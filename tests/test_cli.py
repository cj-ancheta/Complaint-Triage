import json

from complaint_triage import cli
from complaint_triage.cfpb_profile import ProfileError
from complaint_triage.raw_ingestion import RawIngestionError
from complaint_triage.staging import StagingError


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
