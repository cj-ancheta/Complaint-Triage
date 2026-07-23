import json

from complaint_triage import cli
from complaint_triage.analytical_population import PopulationError
from complaint_triage.cfpb_profile import ProfileError
from complaint_triage.majority_baseline import MajorityBaselineError
from complaint_triage.raw_ingestion import RawIngestionError
from complaint_triage.real_extraction import ExtractionError
from complaint_triage.real_run_report import RealRunReportError
from complaint_triage.staging import StagingError
from complaint_triage.taxonomy_profile import TaxonomyProfileError
from complaint_triage.temporal_split import TemporalSplitError


def test_profile_command_prints_safe_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "fetch_cfpb_profile",
        lambda: {
            "status": "ok",
            "result": {"returned_hit_count": 3},
            "privacy": {"source_values_logged": False},
        },
    )

    exit_code = cli.main(["profile-cfpb"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["result"]["returned_hit_count"] == 3
    assert output["privacy"]["source_values_logged"] is False


def test_profile_command_returns_controlled_error_without_exception_text(
    monkeypatch, capsys
) -> None:
    def fail() -> None:
        raise ProfileError(
            "http_error",
            requested_at_utc="2026-07-21T05:00:00+00:00",
            http_status=403,
        )

    monkeypatch.setattr(cli, "fetch_cfpb_profile", fail)

    exit_code = cli.main(["profile-cfpb"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"]["code"] == "http_error"
    assert output["error"]["http_status"] == 403
    assert output["privacy"]["response_body_logged"] is False


def test_ingest_command_prints_safe_reconciliation_result(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "ingest_raw_batch",
        lambda _path: {
            "status": "inserted",
            "batch_id": "cfpb-20260721T050000Z-53db3b7b07c8",
            "expected_record_count": 3,
            "inserted_record_count": 3,
        },
    )

    exit_code = cli.main(["ingest-raw-batch", "--manifest", "data/manifests/cfpb/batch.json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "inserted"
    assert output["expected_record_count"] == output["inserted_record_count"]


def test_ingest_command_returns_controlled_error(monkeypatch, capsys) -> None:
    def fail(_path) -> None:
        raise RawIngestionError("artifact_checksum_mismatch")

    monkeypatch.setattr(cli, "ingest_raw_batch", fail)

    exit_code = cli.main(["ingest-raw-batch", "--manifest", "data/manifests/cfpb/batch.json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"]["code"] == "artifact_checksum_mismatch"
    assert output["privacy"]["raw_payload_logged"] is False


def test_stage_command_prints_reconciled_counts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "stage_raw_batch",
        lambda _batch_id: {
            "status": "staged",
            "input_record_count": 3,
            "accepted_record_count": 2,
            "quarantined_record_count": 1,
            "inserted_record_count": 3,
        },
    )

    exit_code = cli.main(["stage-raw-batch", "--batch-id", "cfpb-20260722T000000Z-aaaaaaaaaaaa"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["input_record_count"] == (
        output["accepted_record_count"] + output["quarantined_record_count"]
    )


def test_stage_command_returns_controlled_error(monkeypatch, capsys) -> None:
    def fail(_batch_id) -> None:
        raise StagingError("raw_batch_not_found")

    monkeypatch.setattr(cli, "stage_raw_batch", fail)

    exit_code = cli.main(["stage-raw-batch", "--batch-id", "cfpb-20260722T000000Z-aaaaaaaaaaaa"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"]["code"] == "raw_batch_not_found"
    assert output["privacy"]["raw_payload_logged"] is False


def test_taxonomy_profile_command_prints_aggregate_report(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "fetch_taxonomy_profile",
        lambda: {
            "status": "ok",
            "request": {"complaint_rows_requested": 0},
            "candidate_window": {"counts_by_product": {"Synthetic product": 3}},
            "privacy": {"narratives_received": False},
        },
    )

    exit_code = cli.main(["profile-taxonomy"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["request"]["complaint_rows_requested"] == 0
    assert output["privacy"]["narratives_received"] is False


def test_taxonomy_profile_command_returns_controlled_error(monkeypatch, capsys) -> None:
    def fail() -> None:
        raise TaxonomyProfileError("http_error", http_status=403)

    monkeypatch.setattr(cli, "fetch_taxonomy_profile", fail)

    exit_code = cli.main(["profile-taxonomy"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"] == {"code": "http_error", "http_status": 403}
    assert output["privacy"]["narratives_received"] is False


def test_population_report_command_prints_aggregate_counts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "report_analytical_population",
        lambda _batch_id: {
            "status": "reported",
            "counts": {
                "input_record_count": 3,
                "eligible_record_count": 2,
                "excluded_record_count": 1,
                "output_record_count": 3,
            },
            "privacy": {"narratives_in_report": False},
        },
    )

    exit_code = cli.main(["report-population", "--batch-id", "cfpb-20260722T000000Z-aaaaaaaaaaaa"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["counts"]["input_record_count"] == output["counts"]["output_record_count"]
    assert output["privacy"]["narratives_in_report"] is False


def test_population_report_command_returns_controlled_error(monkeypatch, capsys) -> None:
    def fail(_batch_id: str) -> None:
        raise PopulationError("staging_batch_not_found")

    monkeypatch.setattr(cli, "report_analytical_population", fail)

    exit_code = cli.main(["report-population", "--batch-id", "cfpb-20260722T000000Z-aaaaaaaaaaaa"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"] == {"code": "staging_batch_not_found"}
    assert output["privacy"]["narratives_in_report"] is False


def test_cleanup_command_is_dry_run_by_default(monkeypatch, capsys) -> None:
    calls = []

    def cleanup(path, *, execute, confirmation):
        calls.append((path, execute, confirmation))
        return {"status": "dry_run", "artifact_files_found": 16}

    monkeypatch.setattr(cli, "cleanup_real_data", cleanup)
    exit_code = cli.main(
        ["cleanup-real-data", "--run-manifest", "data/manifests/cfpb/runs/run.json"]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "dry_run"
    assert calls[0][1:] == (False, None)


def test_cleanup_command_prints_safe_controlled_error(monkeypatch, capsys) -> None:
    def fail(_path, *, execute, confirmation) -> None:
        raise ExtractionError("cleanup_confirmation_invalid")

    monkeypatch.setattr(cli, "cleanup_real_data", fail)
    exit_code = cli.main(
        [
            "cleanup-real-data",
            "--run-manifest",
            "data/manifests/cfpb/runs/run.json",
            "--execute",
            "--confirmation",
            "wrong",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"]["code"] == "cleanup_confirmation_invalid"
    assert output["privacy"]["response_body_logged"] is False


def test_acquire_command_requires_and_forwards_policy_confirmation(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "acquire_real_run",
        lambda *, confirmation: {
            "status": "acquired",
            "confirmation_received": confirmation,
            "privacy": {"response_body_logged": False},
        },
    )

    exit_code = cli.main(["acquire-real-run", "--confirmation", "cfpb-local-120d-v1"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["confirmation_received"] == "cfpb-local-120d-v1"


def test_acquire_command_prints_safe_error(monkeypatch, capsys) -> None:
    def fail(*, confirmation) -> None:
        raise ExtractionError("real_acquisition_requires_clean_commit")

    monkeypatch.setattr(cli, "acquire_real_run", fail)
    exit_code = cli.main(["acquire-real-run", "--confirmation", "wrong"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"]["code"] == "real_acquisition_requires_clean_commit"
    assert output["privacy"]["response_body_logged"] is False


def test_real_run_report_command_prints_aggregate_result(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "report_real_run",
        lambda _path: {
            "run_id": "cfpb-run-20260722T130728Z-aaaaaaaaaaaa",
            "counts": {"input_record_count": 100, "eligible_record_count": 98},
            "privacy": {"contains_row_values": False},
        },
    )
    exit_code = cli.main(["report-real-run", "--run-manifest", "data/manifests/cfpb/runs/run.json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["counts"]["eligible_record_count"] == 98
    assert output["privacy"]["contains_row_values"] is False


def test_real_run_report_command_prints_safe_error(monkeypatch, capsys) -> None:
    def fail(_path) -> None:
        raise RealRunReportError("run_reconciliation_failed", failed_check_count=1)

    monkeypatch.setattr(cli, "report_real_run", fail)
    exit_code = cli.main(["report-real-run", "--run-manifest", "data/manifests/cfpb/runs/run.json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"]["code"] == "run_reconciliation_failed"
    assert output["privacy"]["narratives_in_report"] is False


def test_temporal_split_command_prints_aggregate_result(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "build_temporal_split",
        lambda _path: {
            "run_id": "cfpb-run-20260722T130728Z-aaaaaaaaaaaa",
            "split_counts": {"train": 70, "validation": 15, "test": 15},
            "privacy": {"contains_row_values": False},
        },
    )

    exit_code = cli.main(
        ["build-temporal-split", "--run-manifest", "data/manifests/cfpb/runs/run.json"]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["split_counts"] == {"train": 70, "validation": 15, "test": 15}
    assert output["privacy"]["contains_row_values"] is False


def test_temporal_split_command_prints_safe_error(monkeypatch, capsys) -> None:
    def fail(_path) -> None:
        raise TemporalSplitError("split_reconciliation_failed", failed_check_count=1)

    monkeypatch.setattr(cli, "build_temporal_split", fail)
    exit_code = cli.main(
        ["build-temporal-split", "--run-manifest", "data/manifests/cfpb/runs/run.json"]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"] == {
        "code": "split_reconciliation_failed",
        "failed_check_count": 1,
    }
    assert output["privacy"]["narratives_logged"] is False


def test_majority_baseline_command_prints_aggregate_result(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "evaluate_majority_baseline",
        lambda _path: {
            "model": {"predicted_label": "Synthetic majority"},
            "evaluation": {"test": {"metrics": {"macro_f1": 0.05}}},
            "privacy": {"contains_row_values": False},
        },
    )

    exit_code = cli.main(
        [
            "evaluate-majority-baseline",
            "--split-manifest",
            "data/manifests/cfpb/splits/split.json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["model"]["predicted_label"] == "Synthetic majority"
    assert output["privacy"]["contains_row_values"] is False


def test_majority_baseline_command_prints_safe_error(monkeypatch, capsys) -> None:
    def fail(_path) -> None:
        raise MajorityBaselineError("majority_label_tie", tied_label_count=2)

    monkeypatch.setattr(cli, "evaluate_majority_baseline", fail)
    exit_code = cli.main(
        [
            "evaluate-majority-baseline",
            "--split-manifest",
            "data/manifests/cfpb/splits/split.json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"] == {"code": "majority_label_tie", "tied_label_count": 2}
    assert output["privacy"]["narratives_logged"] is False
