from datetime import UTC, datetime, timedelta

import pytest

from complaint_triage.raw_ingestion import REAL_RETENTION_DEADLINE_UTC
from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.retention_checkpoint import build_retention_checkpoint


def test_checkpoint_is_scheduled_before_warning_window() -> None:
    report = build_retention_checkpoint(REAL_RETENTION_DEADLINE_UTC - timedelta(days=31))

    assert report["status"] == "scheduled"
    assert report["days_remaining"] == 31
    assert report["cleanup_required"] is False
    assert set(report["privacy"].values()) == {False}


def test_checkpoint_is_due_soon_at_thirty_days_and_deadline() -> None:
    warning = build_retention_checkpoint(REAL_RETENTION_DEADLINE_UTC - timedelta(days=30))
    deadline = build_retention_checkpoint(REAL_RETENTION_DEADLINE_UTC)

    assert warning["status"] == "due_soon"
    assert warning["days_remaining"] == 30
    assert deadline["status"] == "due_soon"
    assert deadline["days_remaining"] == 0


def test_checkpoint_is_overdue_one_second_after_deadline() -> None:
    report = build_retention_checkpoint(REAL_RETENTION_DEADLINE_UTC + timedelta(seconds=1))

    assert report["status"] == "overdue"
    assert report["days_remaining"] == 0
    assert report["cleanup_required"] is True
    assert "cleanup-real-data" in report["cleanup_command"]


def test_checkpoint_rejects_naive_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_retention_checkpoint(datetime(2026, 10, 20))


def test_checkpoint_normalizes_aware_time_to_utc() -> None:
    report = build_retention_checkpoint(datetime(2026, 7, 25, tzinfo=UTC))

    assert report["observed_at_utc"] == "2026-07-25T00:00:00Z"


def test_scheduled_checkpoint_is_aggregate_only_and_escalates_due_soon() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/retention-checkpoint.yml").read_text(
        encoding="utf-8"
    )

    for required in (
        'cron: "0 1 * * 1"',
        "workflow_dispatch:",
        "--fail-on due_soon",
        "permissions:\n  contents: read",
    ):
        assert required in workflow
    for prohibited in ("data/raw", "artifacts/", "postgres", "upload-artifact"):
        assert prohibited not in workflow.lower()
