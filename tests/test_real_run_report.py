import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from complaint_triage.real_extraction import (
    ExtractionContext,
    PublishedShard,
    approved_monthly_shards,
    publish_run_manifest,
)
from complaint_triage.real_run_report import (
    RealRunReportError,
    _assemble_report,
    report_real_run,
    safe_real_run_report_error,
)


def evidence(**changes):
    values = {
        "manifest": {
            "run_id": "cfpb-run-20260722T130728Z-aaaaaaaaaaaa",
            "partition": {"shard_count": 16},
            "lineage": {"code_commit_sha": "a" * 40},
            "policy": {"retention_policy_id": "cfpb-local-120d-v1"},
        },
        "manifest_count": 100,
        "raw": (16, 100, 100),
        "staging": (16, 100, 100, 0, 100),
        "population": (16, 100, 98, 2, 100, datetime(2026, 7, 22, tzinfo=UTC)),
        "exclusion_counts": {"language_not_english": 2},
        "product_counts": {"Synthetic product A": 70, "Synthetic product B": 28},
        "language_counts": {"en": 98, "fr": 2},
        "lengths": (10, 1000, 250.25),
    }
    values.update(changes)
    return values


def test_aggregate_report_reconciles_without_row_values() -> None:
    report = _assemble_report(**evidence())

    assert report["status"] == "reported"
    assert report["counts"]["eligible_record_count"] == 98
    assert report["counts"]["eligible_rate"] == 0.98
    assert all(report["checks"].values())
    assert report["privacy"]["contains_row_values"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"raw": (15, 100, 100)},
        {"staging": (16, 100, 99, 0, 100)},
        {"population": (16, 100, 97, 2, 100, datetime(2026, 7, 22, tzinfo=UTC))},
        {"product_counts": {"Synthetic product": 97}},
    ],
)
def test_aggregate_report_fails_closed_on_layer_drift(change: dict) -> None:
    with pytest.raises(RealRunReportError, match="run_reconciliation_failed"):
        _assemble_report(**evidence(**change))


def test_safe_report_error_contains_no_rows() -> None:
    report = safe_real_run_report_error(
        RealRunReportError("run_reconciliation_failed", failed_check_count=1)
    )
    assert report["privacy"] == {"contains_row_values": False, "narratives_in_report": False}


class FakeCursor:
    def __init__(self) -> None:
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def execute(self, query, _parameters) -> None:
        self.query = query

    def fetchone(self):
        if "FROM raw.ingestion_batches" in self.query:
            return (16, 100, 100)
        if "FROM staging.transformation_batches" in self.query:
            return (16, 100, 100, 0, 100)
        if "FROM analytical.population_runs" in self.query:
            return (16, 100, 98, 2, 100, datetime(2026, 7, 22, tzinfo=UTC))
        if "min(narrative_char_count)" in self.query:
            return (10, 1000, 250.25)
        raise AssertionError(self.query)

    def fetchall(self):
        if "unnest(exclusion_reasons)" in self.query:
            return [("language_not_english", 2)]
        if "target_product" in self.query:
            return [("Synthetic product", 98)]
        if "detected_language" in self.query:
            return [("en", 98), ("fr", 2)]
        raise AssertionError(self.query)


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def cursor(self):
        return FakeCursor()


class FakeSettings:
    def psycopg_conninfo(self) -> str:
        return "not-used"


def synthetic_run_manifest(tmp_path: Path) -> Path:
    shards = []
    for spec in approved_monthly_shards():
        digest = hashlib.sha256(spec.month.encode()).hexdigest()
        batch_id = f"cfpb-20260722T120000Z-{digest[:12]}"
        shards.append(
            PublishedShard(
                ordinal=spec.ordinal,
                month=spec.month,
                start_inclusive=spec.start_inclusive,
                end_exclusive=spec.end_exclusive,
                api_date_received_min=spec.api_date_received_min,
                api_date_received_max=spec.api_date_received_max,
                preflight_count=5 if spec.ordinal else 25,
                batch_id=batch_id,
                manifest_relative_path=f"data/manifests/cfpb/{batch_id}.json",
                artifact_relative_path=(f"data/raw/cfpb/sha256/{digest[:2]}/{digest}.json"),
                artifact_sha256=digest,
                artifact_byte_count=100,
                returned_record_count=5 if spec.ordinal else 25,
            )
        )
    context = ExtractionContext(
        run_id="cfpb-run-20260722T120000Z-aaaaaaaaaaaa",
        retrieved_at_utc=datetime(2026, 7, 22, 12, tzinfo=UTC),
        expires_at_utc=datetime(2026, 11, 19, 15, 59, 59, tzinfo=UTC),
        code_commit_sha="a" * 40,
        working_tree_clean=True,
    )
    return publish_run_manifest(shards, context=context, repository_root=tmp_path)


def test_report_command_queries_all_layers_and_atomically_writes_report(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "complaint_triage.real_run_report.psycopg.connect",
        lambda _conninfo: FakeConnection(),
    )
    manifest_path = synthetic_run_manifest(tmp_path)

    report = report_real_run(
        manifest_path,
        repository_root=tmp_path,
        settings=FakeSettings(),
    )

    report_path = (
        tmp_path
        / "data"
        / "manifests"
        / "cfpb"
        / "reports"
        / "cfpb-run-20260722T120000Z-aaaaaaaaaaaa.json"
    )
    assert json.loads(report_path.read_text()) == report
    assert report["counts"]["input_record_count"] == 100
    assert report["eligible_counts_by_product"] == {"Synthetic product": 98}
