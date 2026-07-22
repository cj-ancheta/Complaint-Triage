"""Deterministic raw-to-staging transformations with explicit quarantine reasons."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

import psycopg

from complaint_triage.db import DatabaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRANSFORMATION_VERSION = "1.1.0"
BATCH_ID_PATTERN = re.compile(r"^cfpb-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")


class QuarantineReason(StrEnum):
    SOURCE_RECORD_CHECKSUM_MISMATCH = "source_record_checksum_mismatch"
    COMPLAINT_ID_INVALID = "complaint_id_missing_or_invalid"
    RAW_COMPLAINT_ID_MISMATCH = "raw_complaint_id_mismatch"
    DATE_RECEIVED_INVALID = "date_received_invalid"
    NARRATIVE_INVALID = "narrative_missing_or_invalid"
    PRODUCT_INVALID = "product_missing_or_invalid"
    HAS_NARRATIVE_NOT_TRUE = "has_narrative_not_true"
    DUPLICATE_COMPLAINT_ID = "duplicate_complaint_id_within_batch"


class StagingError(Exception):
    """A controlled staging failure that never contains source values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class RawSourceRow:
    batch_id: str
    ordinal: int
    raw_complaint_id: str
    source_record_sha256: str
    payload: dict[str, Any]
    export_narrative_filter_guaranteed: bool = False


@dataclass(frozen=True)
class StagedOutcome:
    batch_id: str
    ordinal: int
    source_record_sha256: str
    status: str
    reasons: tuple[str, ...]
    complaint_id: str | None
    date_received: date | None
    narrative: str | None
    narrative_sha256: str | None
    product_raw: str | None
    sub_product_raw: str | None
    issue_raw: str | None
    sub_issue_raw: str | None
    submitted_via_raw: str | None


def safe_staging_error(error: StagingError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {"source_values_logged": False, "raw_payload_logged": False},
    }


def transform_raw_rows(rows: tuple[RawSourceRow, ...]) -> tuple[StagedOutcome, ...]:
    """Normalize source-quality fields and assign closed quarantine reasons."""

    normalized_ids = [_normalize_complaint_id(row.payload.get("complaint_id")) for row in rows]
    id_counts = Counter(value for value in normalized_ids if value is not None)

    outcomes: list[StagedOutcome] = []
    for row, complaint_id in zip(rows, normalized_ids, strict=True):
        reasons: list[QuarantineReason] = []
        if _payload_sha256(row.payload) != row.source_record_sha256:
            reasons.append(QuarantineReason.SOURCE_RECORD_CHECKSUM_MISMATCH)
        if complaint_id is None:
            reasons.append(QuarantineReason.COMPLAINT_ID_INVALID)
        elif complaint_id != row.raw_complaint_id:
            reasons.append(QuarantineReason.RAW_COMPLAINT_ID_MISMATCH)
        if complaint_id is not None and id_counts[complaint_id] > 1:
            reasons.append(QuarantineReason.DUPLICATE_COMPLAINT_ID)

        received_date = _normalize_date(row.payload.get("date_received"))
        if received_date is None:
            reasons.append(QuarantineReason.DATE_RECEIVED_INVALID)

        narrative = _normalize_required_text(row.payload.get("complaint_what_happened"))
        if narrative is None:
            reasons.append(QuarantineReason.NARRATIVE_INVALID)

        product = _normalize_required_text(row.payload.get("product"))
        if product is None:
            reasons.append(QuarantineReason.PRODUCT_INVALID)

        if (
            row.payload.get("has_narrative") is not True
            and not row.export_narrative_filter_guaranteed
        ):
            reasons.append(QuarantineReason.HAS_NARRATIVE_NOT_TRUE)

        reason_values = tuple(reason.value for reason in reasons)
        outcomes.append(
            StagedOutcome(
                batch_id=row.batch_id,
                ordinal=row.ordinal,
                source_record_sha256=row.source_record_sha256,
                status="quarantined" if reasons else "accepted",
                reasons=reason_values,
                complaint_id=complaint_id,
                date_received=received_date,
                narrative=narrative,
                narrative_sha256=_text_sha256(narrative),
                product_raw=product,
                sub_product_raw=_normalize_optional_text(row.payload.get("sub_product")),
                issue_raw=_normalize_optional_text(row.payload.get("issue")),
                sub_issue_raw=_normalize_optional_text(row.payload.get("sub_issue")),
                submitted_via_raw=_normalize_optional_text(row.payload.get("submitted_via")),
            )
        )
    return tuple(outcomes)


def stage_raw_batch(
    batch_id: str,
    *,
    settings: DatabaseSettings | None = None,
    repository_root: Path = PROJECT_ROOT,
    transformation_version: str = TRANSFORMATION_VERSION,
) -> dict[str, Any]:
    """Create one immutable version of staging outcomes for a raw batch."""

    if not BATCH_ID_PATTERN.fullmatch(batch_id):
        raise StagingError("batch_id_invalid")
    if transformation_version != TRANSFORMATION_VERSION:
        raise StagingError("transformation_version_unsupported")
    database_settings = settings or DatabaseSettings.from_environment(
        env_file=repository_root / ".env"
    )

    try:
        with psycopg.connect(database_settings.psycopg_conninfo()) as connection:
            with connection.cursor() as cursor:
                rows, expected_count = _load_raw_rows(cursor, batch_id)
                outcomes = transform_raw_rows(rows)
                if len(outcomes) != expected_count:
                    raise StagingError("raw_batch_reconciliation_failed")

                accepted_count = sum(outcome.status == "accepted" for outcome in outcomes)
                quarantined_count = len(outcomes) - accepted_count
                cursor.execute(
                    """
                    INSERT INTO staging.transformation_batches (
                        raw_batch_id,
                        transformation_version,
                        input_record_count,
                        accepted_record_count,
                        quarantined_record_count,
                        output_record_count
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING raw_batch_id
                    """,
                    (
                        batch_id,
                        transformation_version,
                        expected_count,
                        accepted_count,
                        quarantined_count,
                        len(outcomes),
                    ),
                )
                if cursor.fetchone() is None:
                    _verify_existing_transformation(
                        cursor,
                        batch_id=batch_id,
                        transformation_version=transformation_version,
                        expected_count=expected_count,
                        accepted_count=accepted_count,
                        quarantined_count=quarantined_count,
                    )
                    return _result(
                        batch_id,
                        status="already_staged",
                        input_count=expected_count,
                        accepted_count=accepted_count,
                        quarantined_count=quarantined_count,
                        inserted_count=0,
                    )

                cursor.executemany(
                    """
                    INSERT INTO staging.complaint_outcomes (
                        raw_batch_id,
                        source_row_ordinal,
                        transformation_version,
                        source_record_sha256,
                        outcome_status,
                        quarantine_reasons,
                        complaint_id,
                        date_received,
                        narrative,
                        narrative_sha256,
                        product_raw,
                        sub_product_raw,
                        issue_raw,
                        sub_issue_raw,
                        submitted_via_raw
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    [
                        (
                            outcome.batch_id,
                            outcome.ordinal,
                            transformation_version,
                            outcome.source_record_sha256,
                            outcome.status,
                            list(outcome.reasons),
                            outcome.complaint_id,
                            outcome.date_received,
                            outcome.narrative,
                            outcome.narrative_sha256,
                            outcome.product_raw,
                            outcome.sub_product_raw,
                            outcome.issue_raw,
                            outcome.sub_issue_raw,
                            outcome.submitted_via_raw,
                        )
                        for outcome in outcomes
                    ],
                )
    except StagingError:
        raise
    except psycopg.Error as error:
        raise StagingError("database_write_failed") from error

    return _result(
        batch_id,
        status="staged",
        input_count=expected_count,
        accepted_count=accepted_count,
        quarantined_count=quarantined_count,
        inserted_count=len(outcomes),
    )


def _load_raw_rows(
    cursor: psycopg.Cursor[Any], batch_id: str
) -> tuple[tuple[RawSourceRow, ...], int]:
    cursor.execute(
        """
        SELECT returned_record_count,
               COALESCE(
                   manifest #>> '{request,parameters,format}' = 'json'
                   AND manifest #>> '{request,parameters,has_narrative}' = 'true',
                   false
               ) AS export_narrative_filter_guaranteed
        FROM raw.ingestion_batches
        WHERE batch_id = %s
        """,
        (batch_id,),
    )
    batch = cursor.fetchone()
    if batch is None:
        raise StagingError("raw_batch_not_found")
    expected_count = int(batch[0])
    export_narrative_filter_guaranteed = bool(batch[1])

    cursor.execute(
        """
        SELECT batch_id, source_row_ordinal, complaint_id, source_record_sha256, payload
        FROM raw.complaints
        WHERE batch_id = %s
        ORDER BY source_row_ordinal
        """,
        (batch_id,),
    )
    rows = tuple(
        RawSourceRow(
            batch_id=value[0],
            ordinal=value[1],
            raw_complaint_id=value[2],
            source_record_sha256=value[3],
            payload=value[4],
            export_narrative_filter_guaranteed=export_narrative_filter_guaranteed,
        )
        for value in cursor.fetchall()
    )
    if len(rows) != expected_count:
        raise StagingError("raw_batch_reconciliation_failed")
    return rows, expected_count


def _verify_existing_transformation(
    cursor: psycopg.Cursor[Any],
    *,
    batch_id: str,
    transformation_version: str,
    expected_count: int,
    accepted_count: int,
    quarantined_count: int,
) -> None:
    cursor.execute(
        """
        SELECT
            input_record_count,
            accepted_record_count,
            quarantined_record_count,
            output_record_count,
            (
                SELECT count(*)
                FROM staging.complaint_outcomes
                WHERE raw_batch_id = %s AND transformation_version = %s
            ) AS stored_outcome_count
        FROM staging.transformation_batches
        WHERE raw_batch_id = %s AND transformation_version = %s
        """,
        (batch_id, transformation_version, batch_id, transformation_version),
    )
    existing = cursor.fetchone()
    expected = (
        expected_count,
        accepted_count,
        quarantined_count,
        expected_count,
        expected_count,
    )
    if existing is None or tuple(existing) != expected:
        raise StagingError("transformation_identity_conflict")


def _result(
    batch_id: str,
    *,
    status: str,
    input_count: int,
    accepted_count: int,
    quarantined_count: int,
    inserted_count: int,
) -> dict[str, Any]:
    return {
        "status": status,
        "raw_batch_id": batch_id,
        "transformation_version": TRANSFORMATION_VERSION,
        "input_record_count": input_count,
        "accepted_record_count": accepted_count,
        "quarantined_record_count": quarantined_count,
        "inserted_record_count": inserted_count,
        "privacy": {"source_values_logged": False, "raw_payload_logged": False},
    }


def _normalize_complaint_id(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    normalized = unicodedata.normalize("NFC", str(value)).strip()
    return normalized or None


def _normalize_date(value: Any) -> date | None:
    normalized = _normalize_required_text(value)
    if normalized is None:
        return None
    try:
        parsed = date.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == normalized else None


def _normalize_required_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))
    normalized = normalized.strip()
    return normalized or None


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return _normalize_required_text(value)


def _text_sha256(value: str | None) -> str | None:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value is not None else None


def _payload_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
