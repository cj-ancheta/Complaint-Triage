"""Validate and transactionally load content-addressed CFPB raw batches."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import psycopg
from jsonschema import Draft202012Validator, FormatChecker
from psycopg.types.json import Jsonb

from complaint_triage.db import DatabaseSettings
from complaint_triage.taxonomy import (
    MODELLING_WINDOW_END_EXCLUSIVE,
    MODELLING_WINDOW_START,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-raw-batch-manifest.schema.json"
SYNTHETIC_RETENTION_POLICY_ID = "not-applicable-synthetic-fixture"
REAL_RETENTION_POLICY_ID = "cfpb-local-120d-v1"
REAL_RETENTION_DEADLINE_UTC = datetime(2026, 11, 19, 15, 59, 59, tzinfo=UTC)


class RawIngestionError(Exception):
    """A controlled ingestion failure whose details contain no source row values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class RawRecord:
    ordinal: int
    complaint_id: str
    sha256: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class PreparedRawBatch:
    manifest: dict[str, Any]
    records: tuple[RawRecord, ...]


def safe_ingestion_error(error: RawIngestionError) -> dict[str, Any]:
    """Return a CLI-safe error object without raw payload or exception text."""

    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {"source_values_logged": False, "raw_payload_logged": False},
    }


def prepare_raw_batch(
    manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    schema_path: Path = MANIFEST_SCHEMA_PATH,
    now_utc: datetime | None = None,
) -> PreparedRawBatch:
    """Validate manifest, lineage, exact bytes, and aggregate reconciliation."""

    root = repository_root.resolve()
    manifest_file = manifest_path.resolve()
    expected_manifest_directory = (root / "data" / "manifests" / "cfpb").resolve()
    if manifest_file.parent != expected_manifest_directory or manifest_file.suffix != ".json":
        raise RawIngestionError("unsafe_manifest_path")

    manifest = _read_json_object(manifest_file, "manifest")
    schema = _read_json_object(schema_path.resolve(), "manifest_schema")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        path = "/".join(str(part) for part in first.absolute_path) or "root"
        raise RawIngestionError(
            "manifest_schema_invalid",
            issue_count=len(errors),
            first_path=path,
            first_validator=str(first.validator),
        )

    _validate_retention_boundary(manifest, now_utc=now_utc or datetime.now(UTC))

    artifact = manifest["artifact"]
    artifact_relative = PurePosixPath(artifact["relative_path"])
    artifact_path = (root / Path(*artifact_relative.parts)).resolve()
    expected_raw_root = (root / "data" / "raw" / "cfpb" / "sha256").resolve()
    if not artifact_path.is_relative_to(expected_raw_root):
        raise RawIngestionError("unsafe_artifact_path")

    raw_bytes = _read_bytes(artifact_path)
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    expected_relative = f"data/raw/cfpb/sha256/{checksum[:2]}/{checksum}.json"
    if checksum != artifact["sha256"]:
        raise RawIngestionError("artifact_checksum_mismatch")
    if len(raw_bytes) != artifact["byte_count"]:
        raise RawIngestionError("artifact_byte_count_mismatch")
    if artifact["relative_path"] != expected_relative:
        raise RawIngestionError("artifact_content_address_mismatch")

    expected_request_fingerprint = hashlib.sha256(_canonical_request_bytes(manifest)).hexdigest()
    if manifest["request"]["request_fingerprint_sha256"] != expected_request_fingerprint:
        raise RawIngestionError("request_fingerprint_mismatch")

    compact_timestamp = manifest["response"]["retrieved_at_utc"].replace("-", "").replace(":", "")
    expected_batch_id = f"cfpb-{compact_timestamp}-{checksum[:12]}"
    if manifest["batch_id"] != expected_batch_id:
        raise RawIngestionError("batch_id_mismatch")

    response = _decode_json_object(raw_bytes, "artifact")
    records = _reconcile_records(manifest, response)
    if manifest["is_synthetic"]:
        _validate_synthetic_markers(response, records)
    return PreparedRawBatch(manifest=manifest, records=records)


def _validate_retention_boundary(manifest: dict[str, Any], *, now_utc: datetime) -> None:
    privacy = manifest["privacy"]
    if manifest["is_synthetic"]:
        if manifest["manifest_version"] != "1.0.0":
            raise RawIngestionError("synthetic_manifest_version_unsupported")
        if privacy["retention_policy_id"] != SYNTHETIC_RETENTION_POLICY_ID:
            raise RawIngestionError("synthetic_retention_marker_invalid")
        if "expires_at_utc" in privacy:
            raise RawIngestionError("synthetic_retention_expiry_forbidden")
        return

    if manifest["manifest_version"] != "2.0.0":
        raise RawIngestionError("real_manifest_version_unsupported")
    if privacy["retention_policy_id"] != REAL_RETENTION_POLICY_ID:
        raise RawIngestionError("real_retention_policy_invalid")
    expires_at = privacy.get("expires_at_utc")
    if not isinstance(expires_at, str):
        raise RawIngestionError("real_retention_expiry_missing")
    expiry = _parse_utc(expires_at)
    retrieved_at = _parse_utc(manifest["response"]["retrieved_at_utc"])
    if expiry > REAL_RETENTION_DEADLINE_UTC:
        raise RawIngestionError("real_retention_expiry_exceeds_policy")
    if expiry <= retrieved_at or now_utc >= expiry:
        raise RawIngestionError("real_retention_expired")
    if manifest["lineage"]["working_tree_clean"] is not True:
        raise RawIngestionError("real_acquisition_requires_clean_commit")

    parameters = manifest["request"]["parameters"]
    date_min = str(parameters["date_received_min"])
    date_max = str(parameters["date_received_max"])
    if (
        date_min < MODELLING_WINDOW_START
        or date_max > MODELLING_WINDOW_END_EXCLUSIVE
        or date_min >= date_max
    ):
        raise RawIngestionError("real_request_outside_approved_window")


def ingest_raw_batch(
    manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
) -> dict[str, Any]:
    """Insert one validated batch exactly once in a single database transaction."""

    prepared = prepare_raw_batch(manifest_path, repository_root=repository_root)
    manifest = prepared.manifest
    database_settings = settings or DatabaseSettings.from_environment(
        env_file=repository_root / ".env"
    )

    try:
        with psycopg.connect(database_settings.psycopg_conninfo()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO raw.ingestion_batches (
                        batch_id,
                        manifest_version,
                        is_synthetic,
                        request_fingerprint_sha256,
                        artifact_sha256,
                        artifact_relative_path,
                        artifact_byte_count,
                        retrieved_at,
                        returned_record_count,
                        inserted_record_count,
                        retention_policy_id,
                        manifest
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING batch_id
                    """,
                    (
                        manifest["batch_id"],
                        manifest["manifest_version"],
                        manifest["is_synthetic"],
                        manifest["request"]["request_fingerprint_sha256"],
                        manifest["artifact"]["sha256"],
                        manifest["artifact"]["relative_path"],
                        manifest["artifact"]["byte_count"],
                        _parse_utc(manifest["response"]["retrieved_at_utc"]),
                        len(prepared.records),
                        len(prepared.records),
                        manifest["privacy"]["retention_policy_id"],
                        Jsonb(manifest),
                    ),
                )
                inserted_batch = cursor.fetchone()
                if inserted_batch is None:
                    _verify_existing_batch(cursor, prepared)
                    return _result(prepared, status="already_ingested", inserted_count=0)

                cursor.executemany(
                    """
                    INSERT INTO raw.complaints (
                        batch_id,
                        source_row_ordinal,
                        complaint_id,
                        source_record_sha256,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            manifest["batch_id"],
                            record.ordinal,
                            record.complaint_id,
                            record.sha256,
                            Jsonb(record.payload),
                        )
                        for record in prepared.records
                    ],
                )
    except RawIngestionError:
        raise
    except psycopg.Error as error:
        raise RawIngestionError("database_write_failed") from error

    return _result(prepared, status="inserted", inserted_count=len(prepared.records))


def _verify_existing_batch(cursor: psycopg.Cursor[Any], prepared: PreparedRawBatch) -> None:
    manifest = prepared.manifest
    cursor.execute(
        """
        SELECT
            batch_id,
            request_fingerprint_sha256,
            artifact_sha256,
            returned_record_count,
            (
                SELECT count(*)
                FROM raw.complaints
                WHERE raw.complaints.batch_id = raw.ingestion_batches.batch_id
            ) AS stored_record_count
        FROM raw.ingestion_batches
        WHERE batch_id = %s
           OR (request_fingerprint_sha256 = %s AND artifact_sha256 = %s)
        """,
        (
            manifest["batch_id"],
            manifest["request"]["request_fingerprint_sha256"],
            manifest["artifact"]["sha256"],
        ),
    )
    existing = cursor.fetchone()
    expected = (
        manifest["batch_id"],
        manifest["request"]["request_fingerprint_sha256"],
        manifest["artifact"]["sha256"],
        len(prepared.records),
        len(prepared.records),
    )
    if existing is None or tuple(existing) != expected:
        raise RawIngestionError("batch_identity_conflict")


def _result(prepared: PreparedRawBatch, *, status: str, inserted_count: int) -> dict[str, Any]:
    manifest = prepared.manifest
    return {
        "status": status,
        "batch_id": manifest["batch_id"],
        "request_fingerprint_sha256": manifest["request"]["request_fingerprint_sha256"],
        "artifact_sha256": manifest["artifact"]["sha256"],
        "expected_record_count": len(prepared.records),
        "inserted_record_count": inserted_count,
        "privacy": {"source_values_logged": False, "raw_payload_logged": False},
    }


def _reconcile_records(manifest: dict[str, Any], response: dict[str, Any]) -> tuple[RawRecord, ...]:
    try:
        hits_container = response["hits"]
        hits = hits_container["hits"]
        total = hits_container["total"]
        metadata = response["_meta"]
    except (KeyError, TypeError) as error:
        raise RawIngestionError("artifact_envelope_invalid") from error
    if not isinstance(hits, list) or not isinstance(total, dict) or not isinstance(metadata, dict):
        raise RawIngestionError("artifact_envelope_invalid")

    sources: list[dict[str, Any]] = []
    complaint_ids: list[str] = []
    complaint_id_types: set[str] = set()
    narratives: list[str] = []
    dates: list[str] = []
    raw_records: list[RawRecord] = []
    for ordinal, hit in enumerate(hits):
        if not isinstance(hit, dict) or not isinstance(hit.get("_source"), dict):
            raise RawIngestionError("artifact_record_invalid", source_row_ordinal=ordinal)
        source = hit["_source"]
        complaint_id = source.get("complaint_id")
        if isinstance(complaint_id, bool) or not isinstance(complaint_id, (str, int)):
            raise RawIngestionError("complaint_id_invalid", source_row_ordinal=ordinal)
        complaint_id_types.add("integer" if isinstance(complaint_id, int) else "string")
        complaint_ids.append(str(complaint_id))
        narrative = source.get("complaint_what_happened")
        if isinstance(narrative, str) and narrative.strip():
            narratives.append(narrative)
        received_date = source.get("date_received")
        if not isinstance(received_date, str):
            raise RawIngestionError("date_received_invalid", source_row_ordinal=ordinal)
        dates.append(received_date)
        sources.append(source)
        source_bytes = json.dumps(
            source,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        raw_records.append(
            RawRecord(
                ordinal=ordinal,
                complaint_id=str(complaint_id),
                sha256=hashlib.sha256(source_bytes).hexdigest(),
                payload=source,
            )
        )

    records = manifest["records"]
    schema_observation = manifest["schema_observation"]
    observed_fields = sorted({field for source in sources for field in source})
    expected_values = {
        "returned_record_count": len(sources),
        "matching_total": total.get("value"),
        "matching_total_relation": total.get("relation"),
        "unique_complaint_id_count": len(set(complaint_ids)),
        "duplicate_complaint_id_count": len(complaint_ids) - len(set(complaint_ids)),
        "non_empty_narrative_count": len(narratives),
        "observed_date_received_min": min(dates) if dates else None,
        "observed_date_received_max": max(dates) if dates else None,
    }
    for field, expected in expected_values.items():
        if records.get(field) != expected:
            raise RawIngestionError("record_reconciliation_failed", field=field)
    if len(sources) > int(manifest["request"]["parameters"]["size"]):
        raise RawIngestionError("bounded_request_limit_exceeded")

    if schema_observation["source_fields"] != observed_fields:
        raise RawIngestionError("schema_observation_mismatch", field="source_fields")
    if schema_observation["field_count"] != len(observed_fields):
        raise RawIngestionError("schema_observation_mismatch", field="field_count")
    if sorted(schema_observation["complaint_id_observed_types"]) != sorted(complaint_id_types):
        raise RawIngestionError("schema_observation_mismatch", field="complaint_id_observed_types")

    metadata_mapping = {
        "last_indexed": "source_last_indexed",
        "last_updated": "source_last_updated",
        "license": "source_license",
        "total_record_count": "total_record_count",
        "has_data_issue": "has_data_issue",
        "is_data_stale": "is_data_stale",
        "is_narrative_stale": "is_narrative_stale",
    }
    for source_field, manifest_field in metadata_mapping.items():
        if metadata.get(source_field) != manifest["response"][manifest_field]:
            raise RawIngestionError("response_metadata_mismatch", field=manifest_field)

    return tuple(raw_records)


def _validate_synthetic_markers(response: dict[str, Any], records: tuple[RawRecord, ...]) -> None:
    hits = response["hits"]["hits"]
    for ordinal, (hit, record) in enumerate(zip(hits, records, strict=True)):
        narrative = record.payload.get("complaint_what_happened")
        if (
            not record.complaint_id.startswith("SYN-")
            or "synthetic" not in str(hit.get("_index", "")).lower()
            or not isinstance(narrative, str)
            or not narrative.startswith("SYNTHETIC TEST RECORD.")
        ):
            raise RawIngestionError("synthetic_marker_invalid", source_row_ordinal=ordinal)


def _canonical_request_bytes(manifest: dict[str, Any]) -> bytes:
    request = manifest["request"]
    value = {
        "base_url": request["base_url"],
        "endpoint_id": manifest["source"]["endpoint_id"],
        "method": request["method"],
        "parameters": request["parameters"],
        "schema": request["fingerprint_schema"],
    }
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _read_json_object(path: Path, kind: str) -> dict[str, Any]:
    try:
        return _decode_json_object(path.read_bytes(), kind)
    except OSError as error:
        raise RawIngestionError(f"{kind}_unreadable") from error


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise RawIngestionError("artifact_unreadable") from error


def _decode_json_object(raw_bytes: bytes, kind: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw_bytes,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise RawIngestionError(f"{kind}_json_invalid") from error
    if not isinstance(value, dict):
        raise RawIngestionError(f"{kind}_json_invalid")
    return value
