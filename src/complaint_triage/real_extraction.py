"""Fail-closed primitives for the approved monthly CFPB export run."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import ijson
from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.raw_ingestion import (
    MANIFEST_SCHEMA_PATH,
    REAL_RETENTION_DEADLINE_UTC,
    REAL_RETENTION_POLICY_ID,
)
from complaint_triage.taxonomy import (
    MODELLING_WINDOW_END_EXCLUSIVE,
    MODELLING_WINDOW_START,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-extraction-run-manifest.schema.json"
API_CONTRACT_COMMIT = "f10324b3e42c146fc6de1caacfb0bb63691e6b4a"
EXPORT_LIMIT = 100_000
SHARD_BYTE_LIMIT = 1_073_741_824
EXPECTED_SHARD_COUNT = 16
POSTGRES_VOLUME = "complaint-triage-ml_postgres_data"
RUN_ID_PATTERN = re.compile(r"^cfpb-run-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class ExtractionError(Exception):
    """Controlled extraction failure that never carries complaint values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class ShardSpec:
    ordinal: int
    month: str
    start_inclusive: str
    end_exclusive: str
    api_date_received_min: str
    api_date_received_max: str


@dataclass(frozen=True)
class StreamResponse:
    status_code: int
    content_type: str
    redirected: bool
    chunks: Iterable[bytes]


@dataclass(frozen=True)
class ExtractionContext:
    run_id: str
    retrieved_at_utc: datetime
    expires_at_utc: datetime
    code_commit_sha: str
    working_tree_clean: bool
    python_version: str = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )


@dataclass(frozen=True)
class PublishedShard:
    ordinal: int
    month: str
    start_inclusive: str
    end_exclusive: str
    api_date_received_min: str
    api_date_received_max: str
    preflight_count: int
    batch_id: str
    manifest_relative_path: str
    artifact_relative_path: str
    artifact_sha256: str
    artifact_byte_count: int
    returned_record_count: int
    artifact_created: bool = field(default=False, compare=False, repr=False)
    manifest_created: bool = field(default=False, compare=False, repr=False)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""


def safe_extraction_error(error: ExtractionError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {"source_values_logged": False, "response_body_logged": False},
    }


def approved_monthly_shards() -> tuple[ShardSpec, ...]:
    """Return the only date partition authorized by ADR 0007 and ADR 0009."""

    start = date.fromisoformat(MODELLING_WINDOW_START)
    end = date.fromisoformat(MODELLING_WINDOW_END_EXCLUSIVE)
    shards: list[ShardSpec] = []
    current = start
    while current < end:
        following = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
        shards.append(
            ShardSpec(
                ordinal=len(shards),
                month=current.strftime("%Y-%m"),
                start_inclusive=current.isoformat(),
                end_exclusive=following.isoformat(),
                api_date_received_min=current.isoformat(),
                api_date_received_max=(following - timedelta(days=1)).isoformat(),
            )
        )
        current = following
    if len(shards) != EXPECTED_SHARD_COUNT or current != end:
        raise ExtractionError("approved_partition_invalid")
    return tuple(shards)


def validate_preflight_counts(counts: Mapping[str, int]) -> dict[str, int]:
    expected_months = [shard.month for shard in approved_monthly_shards()]
    if set(counts) != set(expected_months):
        raise ExtractionError("preflight_partition_mismatch")
    normalized: dict[str, int] = {}
    for month in expected_months:
        value = counts[month]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ExtractionError("preflight_count_invalid", month=month)
        if value >= EXPORT_LIMIT:
            raise ExtractionError("preflight_export_limit_reached", month=month, count=value)
        normalized[month] = value
    return normalized


def export_parameters(spec: ShardSpec, expected_count: int) -> dict[str, str]:
    if expected_count < 1 or expected_count >= EXPORT_LIMIT:
        raise ExtractionError("preflight_count_invalid", month=spec.month)
    return {
        "date_received_min": spec.api_date_received_min,
        "date_received_max": spec.api_date_received_max,
        "format": "json",
        "has_narrative": "true",
        "no_aggs": "true",
        "no_highlight": "true",
        "size": str(expected_count),
        "sort": "created_date_asc",
    }


def publish_export_shard(
    spec: ShardSpec,
    *,
    expected_count: int,
    response: StreamResponse,
    context: ExtractionContext,
    repository_root: Path = PROJECT_ROOT,
    byte_limit: int = SHARD_BYTE_LIMIT,
) -> PublishedShard:
    """Stream, inspect, and atomically publish one content-addressed export."""

    _validate_context(context)
    if spec not in approved_monthly_shards():
        raise ExtractionError("shard_not_approved")
    parameters = export_parameters(spec, expected_count)
    media_type = response.content_type.partition(";")[0].strip().lower()
    if response.redirected:
        raise ExtractionError("export_redirect_rejected", month=spec.month)
    if response.status_code != 200:
        raise ExtractionError(
            "export_http_status_invalid", month=spec.month, status=response.status_code
        )
    if media_type not in {"application/json", "text/json"}:
        raise ExtractionError("export_content_type_invalid", month=spec.month)
    if byte_limit < 1 or byte_limit > SHARD_BYTE_LIMIT:
        raise ExtractionError("export_byte_limit_invalid")

    root = repository_root.resolve()
    temp_directory = (root / "data" / "raw" / "cfpb" / ".tmp" / context.run_id).resolve()
    expected_temp_root = (root / "data" / "raw" / "cfpb" / ".tmp").resolve()
    if not temp_directory.is_relative_to(expected_temp_root):
        raise ExtractionError("unsafe_temporary_path")
    temp_directory.mkdir(parents=True, exist_ok=True)
    temp_path = temp_directory / f"{spec.month}-{uuid.uuid4().hex}.part"
    published_artifact: Path | None = None
    created_artifact = False
    try:
        checksum = hashlib.sha256()
        byte_count = 0
        with temp_path.open("xb") as destination:
            try:
                for chunk in response.chunks:
                    if not isinstance(chunk, bytes):
                        raise ExtractionError("export_chunk_invalid", month=spec.month)
                    byte_count += len(chunk)
                    if byte_count > byte_limit:
                        raise ExtractionError("export_byte_limit_exceeded", month=spec.month)
                    checksum.update(chunk)
                    destination.write(chunk)
            except ExtractionError:
                raise
            except Exception as error:
                raise ExtractionError("export_stream_interrupted", month=spec.month) from error
            destination.flush()
            os.fsync(destination.fileno())
        if byte_count == 0:
            raise ExtractionError("export_empty", month=spec.month)

        observation = _inspect_export(temp_path, spec, expected_count)
        digest = checksum.hexdigest()
        artifact_relative = f"data/raw/cfpb/sha256/{digest[:2]}/{digest}.json"
        artifact_path = (root / Path(*artifact_relative.split("/"))).resolve()
        expected_artifact_root = (root / "data" / "raw" / "cfpb" / "sha256").resolve()
        if not artifact_path.is_relative_to(expected_artifact_root):
            raise ExtractionError("unsafe_artifact_path")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        if artifact_path.exists():
            if artifact_path.stat().st_size != byte_count or _file_sha256(artifact_path) != digest:
                raise ExtractionError("artifact_identity_conflict", month=spec.month)
            temp_path.unlink()
        else:
            os.replace(temp_path, artifact_path)
            created_artifact = True
        published_artifact = artifact_path

        manifest = _build_batch_manifest(
            spec,
            expected_count=expected_count,
            context=context,
            content_type=media_type,
            artifact_relative=artifact_relative,
            artifact_sha256=digest,
            artifact_byte_count=byte_count,
            observation=observation,
            parameters=parameters,
        )
        batch_schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
        batch_errors = list(
            Draft202012Validator(batch_schema, format_checker=FormatChecker()).iter_errors(manifest)
        )
        if batch_errors:
            raise ExtractionError("batch_manifest_schema_invalid", issue_count=len(batch_errors))
        manifest_relative = f"data/manifests/cfpb/{manifest['batch_id']}.json"
        manifest_path = (root / Path(*manifest_relative.split("/"))).resolve()
        manifest_created = _atomic_json(manifest_path, manifest)
        return PublishedShard(
            ordinal=spec.ordinal,
            month=spec.month,
            start_inclusive=spec.start_inclusive,
            end_exclusive=spec.end_exclusive,
            api_date_received_min=spec.api_date_received_min,
            api_date_received_max=spec.api_date_received_max,
            preflight_count=expected_count,
            batch_id=manifest["batch_id"],
            manifest_relative_path=manifest_relative,
            artifact_relative_path=artifact_relative,
            artifact_sha256=digest,
            artifact_byte_count=byte_count,
            returned_record_count=observation["returned_record_count"],
            artifact_created=created_artifact,
            manifest_created=manifest_created,
        )
    except ExtractionError:
        if temp_path.exists():
            temp_path.unlink()
        if created_artifact and published_artifact is not None and published_artifact.exists():
            published_artifact.unlink()
        raise
    except (OSError, ijson.JSONError, UnicodeError) as error:
        if temp_path.exists():
            temp_path.unlink()
        if created_artifact and published_artifact is not None and published_artifact.exists():
            published_artifact.unlink()
        raise ExtractionError("export_publication_failed", month=spec.month) from error
    except Exception as error:
        if temp_path.exists():
            temp_path.unlink()
        if created_artifact and published_artifact is not None and published_artifact.exists():
            published_artifact.unlink()
        raise ExtractionError("export_publication_failed", month=spec.month) from error


def publish_run_manifest(
    shards: Sequence[PublishedShard],
    *,
    context: ExtractionContext,
    repository_root: Path = PROJECT_ROOT,
) -> Path:
    _validate_context(context)
    approved = approved_monthly_shards()
    ordered = sorted(shards, key=lambda shard: shard.ordinal)
    if len(ordered) != EXPECTED_SHARD_COUNT:
        raise ExtractionError("run_shard_count_invalid")
    if (
        len({shard.batch_id for shard in ordered}) != EXPECTED_SHARD_COUNT
        or len({shard.artifact_relative_path for shard in ordered}) != EXPECTED_SHARD_COUNT
    ):
        raise ExtractionError("run_shard_identity_duplicate")
    for spec, shard in zip(approved, ordered, strict=True):
        if (
            shard.ordinal != spec.ordinal
            or shard.month != spec.month
            or shard.start_inclusive != spec.start_inclusive
            or shard.end_exclusive != spec.end_exclusive
            or shard.api_date_received_min != spec.api_date_received_min
            or shard.api_date_received_max != spec.api_date_received_max
            or shard.preflight_count != shard.returned_record_count
            or shard.artifact_relative_path
            != f"data/raw/cfpb/sha256/{shard.artifact_sha256[:2]}/{shard.artifact_sha256}.json"
            or shard.manifest_relative_path != f"data/manifests/cfpb/{shard.batch_id}.json"
        ):
            raise ExtractionError("run_shard_reconciliation_failed", month=spec.month)
    manifest = {
        "run_manifest_version": "1.0.0",
        "run_id": context.run_id,
        "created_at_utc": _utc_text(context.retrieved_at_utc),
        "policy": {
            "retention_policy_id": REAL_RETENTION_POLICY_ID,
            "expires_at_utc": _utc_text(context.expires_at_utc),
        },
        "lineage": {
            "code_commit_sha": context.code_commit_sha,
            "working_tree_clean": context.working_tree_clean,
            "api_contract_commit_sha": API_CONTRACT_COMMIT,
        },
        "partition": {
            "window_start_inclusive": MODELLING_WINDOW_START,
            "window_end_exclusive": MODELLING_WINDOW_END_EXCLUSIVE,
            "shard_count": EXPECTED_SHARD_COUNT,
            "export_record_limit": EXPORT_LIMIT,
            "shard_byte_limit": SHARD_BYTE_LIMIT,
        },
        "database_volume": POSTGRES_VOLUME,
        "shards": [
            {
                key: value
                for key, value in asdict(shard).items()
                if key not in {"artifact_created", "manifest_created"}
            }
            for shard in ordered
        ],
        "privacy": {"contains_row_values": False, "git_tracking_allowed": True},
    }
    schema = json.loads(RUN_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)
    )
    if errors:
        raise ExtractionError("run_manifest_schema_invalid", issue_count=len(errors))
    path = (
        repository_root.resolve()
        / "data"
        / "manifests"
        / "cfpb"
        / "runs"
        / f"{context.run_id}.json"
    )
    _atomic_json(path, manifest)
    return path


def cleanup_real_data(
    run_manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    execute: bool = False,
    confirmation: str | None = None,
    command_runner: Callable[[Sequence[str], Path], CommandResult] | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Inventory or delete only artifacts named by one validated run manifest."""

    root = repository_root.resolve()
    expected_runs = (root / "data" / "manifests" / "cfpb" / "runs").resolve()
    manifest_path = run_manifest_path.resolve()
    if manifest_path.parent != expected_runs:
        raise ExtractionError("unsafe_run_manifest_path")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    schema = json.loads(RUN_SCHEMA_PATH.read_text(encoding="utf-8"))
    if list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)):
        raise ExtractionError("run_manifest_schema_invalid")

    artifact_paths: list[Path] = []
    artifact_root = (root / "data" / "raw" / "cfpb" / "sha256").resolve()
    for shard in manifest["shards"]:
        path = (root / Path(*shard["artifact_relative_path"].split("/"))).resolve()
        if not path.is_relative_to(artifact_root):
            raise ExtractionError("unsafe_cleanup_artifact_path")
        artifact_paths.append(path)
    temp_directory = (root / "data" / "raw" / "cfpb" / ".tmp" / manifest["run_id"]).resolve()
    temp_root = (root / "data" / "raw" / "cfpb" / ".tmp").resolve()
    if not temp_directory.is_relative_to(temp_root):
        raise ExtractionError("unsafe_cleanup_temporary_path")

    existing_before = [path for path in artifact_paths if path.is_file()]
    if not execute:
        return _cleanup_report(manifest, "dry_run", existing_before, [], False, False, now_utc)
    if confirmation != manifest["run_id"]:
        raise ExtractionError("cleanup_confirmation_invalid")

    temporary_paths: list[Path] = []
    if temp_directory.exists():
        for child in temp_directory.iterdir():
            if not child.is_file() or child.suffix != ".part":
                raise ExtractionError("unsafe_cleanup_temporary_entry")
            temporary_paths.append(child)
    for path in existing_before:
        path.unlink()
    if temp_directory.exists():
        for path in temporary_paths:
            path.unlink()
        temp_directory.rmdir()
    runner = command_runner or _run_cleanup_command
    down = runner(("docker", "compose", "down", "--volumes", "--remove-orphans"), root)
    volume_check = runner(("docker", "volume", "inspect", POSTGRES_VOLUME), root)
    container_check = runner(("docker", "compose", "ps", "-q"), root)
    database_removed = down.returncode == 0 and volume_check.returncode != 0
    containers_removed = container_check.returncode == 0 and not container_check.stdout.strip()
    if (
        not database_removed
        or not containers_removed
        or any(path.exists() for path in artifact_paths)
    ):
        raise ExtractionError("cleanup_verification_failed")

    report = _cleanup_report(
        manifest,
        "deleted",
        existing_before,
        artifact_paths,
        database_removed,
        containers_removed,
        now_utc,
    )
    evidence_path = (
        root / "data" / "manifests" / "cfpb" / "deletions" / f"{manifest['run_id']}.json"
    )
    _atomic_json(evidence_path, report)
    return report


def _inspect_export(path: Path, spec: ShardSpec, expected_count: int) -> dict[str, Any]:
    count = 0
    complaint_ids: set[str] = set()
    fields: set[str] = set()
    id_types: set[str] = set()
    observed_dates: list[str] = []
    try:
        with path.open("rb") as source_file:
            first_non_whitespace = next(
                (byte for byte in iter(lambda: source_file.read(1), b"") if not byte.isspace()),
                b"",
            )
            if first_non_whitespace != b"[":
                raise ExtractionError("export_envelope_invalid", month=spec.month)
            source_file.seek(0)
            for hit in ijson.items(source_file, "item"):
                ordinal = count
                count += 1
                if not isinstance(hit, dict) or not isinstance(hit.get("_source"), dict):
                    raise ExtractionError("export_record_invalid", source_row_ordinal=ordinal)
                source = hit["_source"]
                required = {
                    "complaint_id",
                    "complaint_what_happened",
                    "date_received",
                    "product",
                }
                if not required.issubset(source):
                    raise ExtractionError("export_schema_drift", source_row_ordinal=ordinal)
                complaint_id = source["complaint_id"]
                if isinstance(complaint_id, bool) or not isinstance(complaint_id, (str, int)):
                    raise ExtractionError("export_complaint_id_invalid", source_row_ordinal=ordinal)
                normalized_id = str(complaint_id)
                if normalized_id in complaint_ids:
                    raise ExtractionError(
                        "export_duplicate_complaint_id", source_row_ordinal=ordinal
                    )
                complaint_ids.add(normalized_id)
                id_types.add("integer" if isinstance(complaint_id, int) else "string")
                narrative = source["complaint_what_happened"]
                if (
                    not isinstance(narrative, str)
                    or not narrative.strip()
                    or ("has_narrative" in source and source["has_narrative"] is not True)
                ):
                    raise ExtractionError("export_narrative_invalid", source_row_ordinal=ordinal)
                if not isinstance(source["product"], str) or not source["product"].strip():
                    raise ExtractionError("export_product_invalid", source_row_ordinal=ordinal)
                received = source["date_received"]
                if not isinstance(received, str):
                    raise ExtractionError("export_date_invalid", source_row_ordinal=ordinal)
                try:
                    received_date = date.fromisoformat(received)
                except ValueError as error:
                    raise ExtractionError(
                        "export_date_invalid", source_row_ordinal=ordinal
                    ) from error
                if (
                    not date.fromisoformat(spec.start_inclusive)
                    <= received_date
                    < date.fromisoformat(spec.end_exclusive)
                ):
                    raise ExtractionError("export_date_outside_shard", source_row_ordinal=ordinal)
                observed_dates.append(received)
                fields.update(source)
    except ijson.JSONError as error:
        raise ExtractionError("export_json_invalid", month=spec.month) from error
    if count != expected_count:
        raise ExtractionError(
            "export_count_mismatch", month=spec.month, expected=expected_count, observed=count
        )
    return {
        "returned_record_count": count,
        "unique_complaint_id_count": len(complaint_ids),
        "duplicate_complaint_id_count": 0,
        "non_empty_narrative_count": count,
        "observed_date_received_min": min(observed_dates),
        "observed_date_received_max": max(observed_dates),
        "source_fields": sorted(fields),
        "complaint_id_observed_types": sorted(id_types),
    }


def _build_batch_manifest(
    spec: ShardSpec,
    *,
    expected_count: int,
    context: ExtractionContext,
    content_type: str,
    artifact_relative: str,
    artifact_sha256: str,
    artifact_byte_count: int,
    observation: dict[str, Any],
    parameters: dict[str, str],
) -> dict[str, Any]:
    request_value = {
        "base_url": "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/",
        "endpoint_id": "cfpb_complaint_search_v1",
        "method": "GET",
        "parameters": parameters,
        "schema": "complaint-triage-request-fingerprint-v1",
    }
    fingerprint = hashlib.sha256(_canonical_json(request_value)).hexdigest()
    timestamp = _utc_text(context.retrieved_at_utc)
    batch_id = f"cfpb-{timestamp.replace('-', '').replace(':', '')}-{artifact_sha256[:12]}"
    return {
        "manifest_version": "2.0.0",
        "batch_id": batch_id,
        "is_synthetic": False,
        "created_at_utc": timestamp,
        "source": {
            "provider": "Consumer Financial Protection Bureau",
            "dataset": "Consumer Complaint Database",
            "endpoint_id": "cfpb_complaint_search_v1",
            "api_contract_repository": "https://github.com/cfpb/ccdb5-api",
            "api_contract_commit_sha": API_CONTRACT_COMMIT,
        },
        "request": {
            "method": "GET",
            "base_url": request_value["base_url"],
            "parameters": parameters,
            "fingerprint_schema": request_value["schema"],
            "request_fingerprint_sha256": fingerprint,
        },
        "response": {
            "retrieved_at_utc": timestamp,
            "http_status": 200,
            "content_type": content_type,
            "content_encoding": "identity",
            "source_last_indexed": None,
            "source_last_updated": None,
            "source_license": None,
            "total_record_count": None,
            "has_data_issue": None,
            "is_data_stale": None,
            "is_narrative_stale": None,
        },
        "artifact": {
            "relative_path": artifact_relative,
            "media_type": "application/json",
            "content_encoding": "identity",
            "byte_count": artifact_byte_count,
            "hash_algorithm": "SHA-256",
            "hash_scope": "stored_bytes",
            "sha256": artifact_sha256,
        },
        "records": {
            "returned_record_count": observation["returned_record_count"],
            "matching_total": expected_count,
            "matching_total_relation": "eq",
            "unique_complaint_id_count": observation["unique_complaint_id_count"],
            "duplicate_complaint_id_count": observation["duplicate_complaint_id_count"],
            "non_empty_narrative_count": observation["non_empty_narrative_count"],
            "observed_date_received_min": observation["observed_date_received_min"],
            "observed_date_received_max": observation["observed_date_received_max"],
        },
        "schema_observation": {
            "field_count": len(observation["source_fields"]),
            "source_fields": observation["source_fields"],
            "complaint_id_observed_types": observation["complaint_id_observed_types"],
        },
        "lineage": {
            "extractor_name": "complaint-triage-monthly-export",
            "extractor_version": "1.0.0",
            "code_commit_sha": context.code_commit_sha,
            "working_tree_clean": context.working_tree_clean,
            "python_version": context.python_version,
        },
        "privacy": {
            "raw_artifact_contains_public_narratives": True,
            "raw_artifact_git_tracked": False,
            "manifest_contains_row_values": False,
            "manifest_git_tracking_allowed": True,
            "retention_policy_id": REAL_RETENTION_POLICY_ID,
            "expires_at_utc": _utc_text(context.expires_at_utc),
        },
    }


def _validate_context(context: ExtractionContext) -> None:
    if not RUN_ID_PATTERN.fullmatch(context.run_id):
        raise ExtractionError("run_id_invalid")
    if not SHA_PATTERN.fullmatch(context.code_commit_sha) or not context.working_tree_clean:
        raise ExtractionError("real_acquisition_requires_clean_commit")
    if context.retrieved_at_utc.tzinfo is None or context.expires_at_utc.tzinfo is None:
        raise ExtractionError("retention_timestamp_invalid")
    if not context.retrieved_at_utc < context.expires_at_utc <= REAL_RETENTION_DEADLINE_UTC:
        raise ExtractionError("retention_boundary_invalid")


def _atomic_json(path: Path, value: dict[str, Any]) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False).encode(
            "utf-8"
        )
        + b"\n"
    )
    if path.exists():
        if path.read_bytes() != encoded:
            raise ExtractionError("manifest_identity_conflict")
        return False
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as destination:
            destination.write(encoded)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
        return True
    finally:
        if temporary.exists():
            temporary.unlink()


def _cleanup_report(
    manifest: dict[str, Any],
    status: str,
    existing_before: Sequence[Path],
    checked_paths: Sequence[Path],
    database_removed: bool,
    containers_removed: bool,
    now_utc: datetime | None,
) -> dict[str, Any]:
    return {
        "deletion_record_version": "1.0.0",
        "run_id": manifest["run_id"],
        "policy_id": manifest["policy"]["retention_policy_id"],
        "recorded_at_utc": _utc_text(now_utc or datetime.now(UTC)),
        "status": status,
        "batch_ids": [shard["batch_id"] for shard in manifest["shards"]],
        "artifact_sha256": [shard["artifact_sha256"] for shard in manifest["shards"]],
        "artifact_files_found": len(existing_before),
        "artifact_files_absent_after": sum(not path.exists() for path in checked_paths),
        "database_volume": manifest["database_volume"],
        "database_volume_removed": database_removed,
        "project_containers_removed": containers_removed,
        "contains_row_values": False,
    }


def _run_cleanup_command(command: Sequence[str], cwd: Path) -> CommandResult:
    completed = subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True)
    return CommandResult(returncode=completed.returncode, stdout=completed.stdout)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
