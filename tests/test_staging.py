import hashlib
import json

import pytest

from complaint_triage.staging import (
    QuarantineReason,
    RawSourceRow,
    StagingError,
    safe_staging_error,
    stage_raw_batch,
    transform_raw_rows,
)


def source_row(
    *,
    ordinal: int = 0,
    raw_complaint_id: str = "SYN-1",
    complaint_id: object = "SYN-1",
    date_received: object = "2024-01-02",
    narrative: object = "  Synthetic narrative.\r\nSecond line.  ",
    product: object = "  Synthetic product  ",
    has_narrative: object = True,
) -> RawSourceRow:
    payload = {
        "complaint_id": complaint_id,
        "date_received": date_received,
        "complaint_what_happened": narrative,
        "product": product,
        "has_narrative": has_narrative,
        "sub_product": "  Sub product  ",
        "issue": "Issue",
        "sub_issue": "   ",
        "submitted_via": None,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return RawSourceRow(
        batch_id="cfpb-20260722T000000Z-aaaaaaaaaaaa",
        ordinal=ordinal,
        raw_complaint_id=raw_complaint_id,
        source_record_sha256=hashlib.sha256(canonical).hexdigest(),
        payload=payload,
    )


def test_valid_row_is_normalized_without_selecting_a_taxonomy() -> None:
    outcome = transform_raw_rows((source_row(),))[0]

    assert outcome.status == "accepted"


def test_export_filter_can_supply_missing_has_narrative_flag() -> None:
    row = source_row()
    payload = dict(row.payload)
    payload.pop("has_narrative")
    canonical = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    export_row = RawSourceRow(
        batch_id=row.batch_id,
        ordinal=row.ordinal,
        raw_complaint_id=row.raw_complaint_id,
        source_record_sha256=hashlib.sha256(canonical).hexdigest(),
        payload=payload,
        export_narrative_filter_guaranteed=True,
    )

    outcome = transform_raw_rows((export_row,))[0]

    assert outcome.status == "accepted"
    assert QuarantineReason.HAS_NARRATIVE_NOT_TRUE.value not in outcome.reasons
    assert outcome.reasons == ()
    assert outcome.date_received.isoformat() == "2024-01-02"
    assert outcome.narrative == "Synthetic narrative.\nSecond line."
    assert len(outcome.narrative_sha256) == 64
    assert outcome.product_raw == "Synthetic product"
    assert outcome.sub_product_raw == "Sub product"
    assert outcome.sub_issue_raw is None
    assert outcome.submitted_via_raw is None


def test_invalid_source_quality_fields_receive_closed_reason_codes() -> None:
    outcome = transform_raw_rows(
        (
            source_row(
                complaint_id=None,
                date_received="01/02/2024",
                narrative="   ",
                product=42,
                has_narrative=False,
            ),
        )
    )[0]

    assert outcome.status == "quarantined"
    assert outcome.reasons == (
        QuarantineReason.COMPLAINT_ID_INVALID.value,
        QuarantineReason.DATE_RECEIVED_INVALID.value,
        QuarantineReason.NARRATIVE_INVALID.value,
        QuarantineReason.PRODUCT_INVALID.value,
        QuarantineReason.HAS_NARRATIVE_NOT_TRUE.value,
    )
    assert outcome.narrative is None
    assert outcome.narrative_sha256 is None


def test_source_identifier_mismatch_is_quarantined() -> None:
    outcome = transform_raw_rows((source_row(raw_complaint_id="SYN-RAW"),))[0]

    assert outcome.reasons == (QuarantineReason.RAW_COMPLAINT_ID_MISMATCH.value,)


def test_source_checksum_mismatch_is_quarantined() -> None:
    row = source_row()
    changed = RawSourceRow(
        batch_id=row.batch_id,
        ordinal=row.ordinal,
        raw_complaint_id=row.raw_complaint_id,
        source_record_sha256="0" * 64,
        payload=row.payload,
    )

    outcome = transform_raw_rows((changed,))[0]

    assert outcome.reasons == (QuarantineReason.SOURCE_RECORD_CHECKSUM_MISMATCH.value,)


def test_every_within_batch_duplicate_is_quarantined_deterministically() -> None:
    rows = (source_row(ordinal=0), source_row(ordinal=1))

    first_run = transform_raw_rows(rows)
    second_run = transform_raw_rows(rows)

    assert first_run == second_run
    assert [outcome.status for outcome in first_run] == ["quarantined", "quarantined"]
    assert all(
        outcome.reasons == (QuarantineReason.DUPLICATE_COMPLAINT_ID.value,) for outcome in first_run
    )


def test_staging_error_report_does_not_contain_source_text() -> None:
    narrative = "This source narrative must not appear."
    report = safe_staging_error(StagingError("database_write_failed"))

    assert narrative not in json.dumps(report)
    assert report["privacy"] == {"source_values_logged": False, "raw_payload_logged": False}


def test_invalid_batch_or_unknown_transformation_version_fails_before_database_access() -> None:
    with pytest.raises(StagingError) as invalid_batch:
        stage_raw_batch("not-a-batch-id")
    assert invalid_batch.value.code == "batch_id_invalid"

    with pytest.raises(StagingError) as unsupported_version:
        stage_raw_batch(
            "cfpb-20260722T000000Z-aaaaaaaaaaaa",
            transformation_version="2.0.0",
        )
    assert unsupported_version.value.code == "transformation_version_unsupported"
