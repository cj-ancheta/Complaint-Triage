import re
from datetime import date

import pytest

from complaint_triage.temporal_split import (
    TemporalSplitError,
    narrative_fingerprint,
    safe_temporal_split_error,
    temporal_assignment,
)


def test_fingerprint_normalizes_unicode_case_and_whitespace() -> None:
    composed = "  CAFÉ\taccount\r\nproblem  "
    decomposed = "cafe\u0301 account problem"

    assert narrative_fingerprint(composed) == narrative_fingerprint(decomposed)
    assert re.fullmatch(r"[0-9a-f]{64}", narrative_fingerprint(composed))


def test_fingerprint_preserves_punctuation_and_numbers() -> None:
    assert narrative_fingerprint("charge 10.00") != narrative_fingerprint("charge 1000")
    assert narrative_fingerprint("not approved") != narrative_fingerprint("not-approved")


@pytest.mark.parametrize(
    ("received", "expected"),
    [
        (date(2023, 9, 1), "train"),
        (date(2024, 8, 31), "train"),
        (date(2024, 9, 1), "validation"),
        (date(2024, 10, 31), "validation"),
        (date(2024, 11, 1), "test"),
        (date(2024, 12, 31), "test"),
    ],
)
def test_temporal_assignment_uses_approved_boundaries(received: date, expected: str) -> None:
    assert temporal_assignment(received) == expected


@pytest.mark.parametrize("received", [date(2023, 8, 31), date(2025, 1, 1)])
def test_temporal_assignment_rejects_dates_outside_window(received: date) -> None:
    with pytest.raises(TemporalSplitError, match="split_date_outside_approved_window"):
        temporal_assignment(received)


def test_safe_error_contains_no_source_values() -> None:
    report = safe_temporal_split_error(
        TemporalSplitError("split_reconciliation_failed", failed_check_count=1)
    )

    assert report["error"] == {
        "code": "split_reconciliation_failed",
        "failed_check_count": 1,
    }
    assert report["privacy"] == {
        "narratives_logged": False,
        "complaint_ids_logged": False,
        "row_values_in_report": False,
    }
