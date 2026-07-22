import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from complaint_triage.raw_ingestion import prepare_raw_batch
from complaint_triage.real_extraction import (
    EXPECTED_SHARD_COUNT,
    POSTGRES_VOLUME,
    CommandResult,
    ExtractionContext,
    ExtractionError,
    PublishedShard,
    StreamResponse,
    approved_monthly_shards,
    cleanup_real_data,
    publish_export_shard,
    publish_run_manifest,
    safe_extraction_error,
    validate_preflight_counts,
)

RETRIEVED = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)
EXPIRY = datetime(2026, 11, 19, 15, 59, 59, tzinfo=UTC)
CONTEXT = ExtractionContext(
    run_id="cfpb-run-20260722T120000Z-aaaaaaaaaaaa",
    retrieved_at_utc=RETRIEVED,
    expires_at_utc=EXPIRY,
    code_commit_sha="b" * 40,
    working_tree_clean=True,
)


def export_bytes(spec_index: int = 0, *, count: int = 2) -> bytes:
    spec = approved_monthly_shards()[spec_index]
    rows = []
    for index in range(count):
        rows.append(
            {
                "_index": "complaints-v1",
                "_source": {
                    "complaint_id": f"TEST-{spec_index}-{index}",
                    "complaint_what_happened": "SYNTHETIC TEST RECORD. No real complaint.",
                    "date_received": spec.start_inclusive,
                    "has_narrative": True,
                    "product": "SYNTHETIC PRODUCT",
                },
            }
        )
    return json.dumps(rows).encode()


def response(raw: bytes, **changes) -> StreamResponse:
    values = {
        "status_code": 200,
        "content_type": "text/json; charset=utf-8",
        "redirected": False,
        "chunks": (raw[:7], raw[7:]),
    }
    values.update(changes)
    return StreamResponse(**values)


def test_approved_partition_maps_half_open_months_to_inclusive_api_dates() -> None:
    shards = approved_monthly_shards()

    assert len(shards) == EXPECTED_SHARD_COUNT
    assert (shards[0].start_inclusive, shards[0].end_exclusive) == ("2023-09-01", "2023-10-01")
    assert shards[0].api_date_received_max == "2023-09-30"
    assert (shards[-1].start_inclusive, shards[-1].end_exclusive) == ("2024-12-01", "2025-01-01")
    assert shards[-1].api_date_received_max == "2024-12-31"


def test_preflight_requires_all_months_below_export_limit() -> None:
    counts = {shard.month: 10 for shard in approved_monthly_shards()}
    assert validate_preflight_counts(counts) == counts

    counts["2024-12"] = 100_000
    with pytest.raises(ExtractionError, match="preflight_export_limit_reached"):
        validate_preflight_counts(counts)


def test_streamed_export_is_validated_and_atomically_published(tmp_path: Path) -> None:
    spec = approved_monthly_shards()[0]
    published = publish_export_shard(
        spec,
        expected_count=2,
        response=response(export_bytes()),
        context=CONTEXT,
        repository_root=tmp_path,
    )

    artifact = tmp_path / Path(*published.artifact_relative_path.split("/"))
    manifest = tmp_path / Path(*published.manifest_relative_path.split("/"))
    assert artifact.read_bytes() == export_bytes()
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == published.artifact_sha256
    assert (
        json.loads(manifest.read_text())["request"]["parameters"]["date_received_max"]
        == "2023-09-30"
    )
    assert (
        len(prepare_raw_batch(manifest, repository_root=tmp_path, now_utc=RETRIEVED).records) == 2
    )
    assert not list((tmp_path / "data" / "raw" / "cfpb" / ".tmp" / CONTEXT.run_id).glob("*.part"))

    replay = publish_export_shard(
        spec,
        expected_count=2,
        response=response(export_bytes()),
        context=CONTEXT,
        repository_root=tmp_path,
    )
    assert replay == published
    assert len(list(artifact.parent.glob("*.json"))) == 1


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"redirected": True}, "export_redirect_rejected"),
        ({"content_type": "text/html"}, "export_content_type_invalid"),
        ({"status_code": 503}, "export_http_status_invalid"),
    ],
)
def test_response_metadata_fails_closed(tmp_path: Path, changes: dict, expected: str) -> None:
    with pytest.raises(ExtractionError, match=expected):
        publish_export_shard(
            approved_monthly_shards()[0],
            expected_count=2,
            response=response(export_bytes(), **changes),
            context=CONTEXT,
            repository_root=tmp_path,
        )


def test_interrupted_stream_leaves_no_part_or_published_artifact(tmp_path: Path) -> None:
    def interrupted():
        yield b"["
        raise ConnectionError("synthetic interruption")

    with pytest.raises(ExtractionError, match="export_stream_interrupted"):
        publish_export_shard(
            approved_monthly_shards()[0],
            expected_count=2,
            response=response(b"", chunks=interrupted()),
            context=CONTEXT,
            repository_root=tmp_path,
        )

    raw_root = tmp_path / "data" / "raw" / "cfpb"
    assert not list(raw_root.rglob("*.part"))
    assert (
        not list((raw_root / "sha256").rglob("*.json")) if (raw_root / "sha256").exists() else True
    )


def test_byte_cap_and_record_reconciliation_fail_before_publication(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError, match="export_byte_limit_exceeded"):
        publish_export_shard(
            approved_monthly_shards()[0],
            expected_count=2,
            response=response(export_bytes()),
            context=CONTEXT,
            repository_root=tmp_path,
            byte_limit=10,
        )

    with pytest.raises(ExtractionError, match="export_count_mismatch"):
        publish_export_shard(
            approved_monthly_shards()[0],
            expected_count=3,
            response=response(export_bytes()),
            context=CONTEXT,
            repository_root=tmp_path,
        )


def test_date_narrative_and_schema_drift_are_rejected(tmp_path: Path) -> None:
    spec = approved_monthly_shards()[0]
    base = json.loads(export_bytes())
    mutations = [
        lambda row: row["_source"].update({"date_received": spec.end_exclusive}),
        lambda row: row["_source"].update({"complaint_what_happened": " "}),
        lambda row: row["_source"].pop("product"),
    ]
    expected = ["export_date_outside_shard", "export_narrative_invalid", "export_schema_drift"]
    for index, (mutation, code) in enumerate(zip(mutations, expected, strict=True)):
        changed = json.loads(json.dumps(base))
        mutation(changed[0])
        isolated = tmp_path / str(index)
        with pytest.raises(ExtractionError, match=code):
            publish_export_shard(
                spec,
                expected_count=2,
                response=response(json.dumps(changed).encode()),
                context=CONTEXT,
                repository_root=isolated,
            )


def test_top_level_object_is_not_accepted_as_export_array(tmp_path: Path) -> None:
    raw = json.dumps({"item": json.loads(export_bytes())[0]}).encode()
    with pytest.raises(ExtractionError, match="export_envelope_invalid"):
        publish_export_shard(
            approved_monthly_shards()[0],
            expected_count=1,
            response=response(raw),
            context=CONTEXT,
            repository_root=tmp_path,
        )


def test_official_export_omission_of_has_narrative_is_accepted(tmp_path: Path) -> None:
    rows = json.loads(export_bytes())
    for row in rows:
        row["_source"].pop("has_narrative")
    published = publish_export_shard(
        approved_monthly_shards()[0],
        expected_count=2,
        response=response(json.dumps(rows).encode()),
        context=CONTEXT,
        repository_root=tmp_path,
    )

    manifest = tmp_path / Path(*published.manifest_relative_path.split("/"))
    assert (
        "has_narrative"
        not in json.loads(manifest.read_text())["schema_observation"]["source_fields"]
    )


def test_truncated_json_is_rejected_without_publication(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError, match="export_json_invalid"):
        publish_export_shard(
            approved_monthly_shards()[0],
            expected_count=1,
            response=response(b'[{"_source":'),
            context=CONTEXT,
            repository_root=tmp_path,
        )
    assert not list((tmp_path / "data" / "raw" / "cfpb").rglob("*.json"))


def fake_shards() -> tuple[PublishedShard, ...]:
    values = []
    for spec in approved_monthly_shards():
        digest = hashlib.sha256(spec.month.encode()).hexdigest()
        batch_id = f"cfpb-20260722T120000Z-{digest[:12]}"
        values.append(
            PublishedShard(
                **as_spec_values(spec),
                preflight_count=10,
                batch_id=batch_id,
                manifest_relative_path=f"data/manifests/cfpb/{batch_id}.json",
                artifact_relative_path=f"data/raw/cfpb/sha256/{digest[:2]}/{digest}.json",
                artifact_sha256=digest,
                artifact_byte_count=100,
                returned_record_count=10,
            )
        )
    return tuple(values)


def as_spec_values(spec) -> dict:
    return {
        "ordinal": spec.ordinal,
        "month": spec.month,
        "start_inclusive": spec.start_inclusive,
        "end_exclusive": spec.end_exclusive,
        "api_date_received_min": spec.api_date_received_min,
        "api_date_received_max": spec.api_date_received_max,
    }


def test_run_contract_requires_exact_reconciled_sixteen_shards(tmp_path: Path) -> None:
    path = publish_run_manifest(fake_shards(), context=CONTEXT, repository_root=tmp_path)
    manifest = json.loads(path.read_text())
    schema = json.loads(
        (
            Path(__file__).parents[1] / "contracts" / "cfpb-extraction-run-manifest.schema.json"
        ).read_text()
    )

    assert len(manifest["shards"]) == 16
    assert list(Draft202012Validator(schema).iter_errors(manifest)) == []
    with pytest.raises(ExtractionError, match="run_shard_count_invalid"):
        publish_run_manifest(fake_shards()[:-1], context=CONTEXT, repository_root=tmp_path)
    drifted = list(fake_shards())
    drifted[0] = replace(drifted[0], returned_record_count=9)
    with pytest.raises(ExtractionError, match="run_shard_reconciliation_failed"):
        publish_run_manifest(drifted, context=CONTEXT, repository_root=tmp_path)


def test_cleanup_dry_run_then_isolated_delete_writes_safe_evidence(tmp_path: Path) -> None:
    run_path = publish_run_manifest(fake_shards(), context=CONTEXT, repository_root=tmp_path)
    for shard in fake_shards():
        artifact = tmp_path / Path(*shard.artifact_relative_path.split("/"))
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"synthetic")
    commands = []

    dry_run = cleanup_real_data(run_path, repository_root=tmp_path, now_utc=RETRIEVED)
    assert dry_run["status"] == "dry_run"
    assert dry_run["artifact_files_found"] == 16

    def runner(command, cwd):
        commands.append((tuple(command), cwd))
        if tuple(command) == ("docker", "volume", "inspect", POSTGRES_VOLUME):
            return CommandResult(returncode=1)
        return CommandResult(returncode=0, stdout="")

    deleted = cleanup_real_data(
        run_path,
        repository_root=tmp_path,
        execute=True,
        confirmation=CONTEXT.run_id,
        command_runner=runner,
        now_utc=RETRIEVED,
    )
    assert deleted["status"] == "deleted"
    assert deleted["artifact_files_absent_after"] == 16
    assert deleted["database_volume"] == POSTGRES_VOLUME
    assert deleted["database_volume_removed"] is True
    assert deleted["project_containers_removed"] is True
    assert commands == [
        (("docker", "compose", "down", "--volumes", "--remove-orphans"), tmp_path.resolve()),
        (("docker", "volume", "inspect", POSTGRES_VOLUME), tmp_path.resolve()),
        (("docker", "compose", "ps", "-q"), tmp_path.resolve()),
    ]
    assert not any(
        (tmp_path / Path(*shard.artifact_relative_path.split("/"))).exists()
        for shard in fake_shards()
    )
    assert "SYNTHETIC TEST RECORD" not in json.dumps(deleted)


def test_cleanup_requires_exact_confirmation_and_safe_manifest_location(tmp_path: Path) -> None:
    run_path = publish_run_manifest(fake_shards(), context=CONTEXT, repository_root=tmp_path)
    with pytest.raises(ExtractionError, match="cleanup_confirmation_invalid"):
        cleanup_real_data(run_path, repository_root=tmp_path, execute=True, confirmation="wrong")
    with pytest.raises(ExtractionError, match="unsafe_run_manifest_path"):
        cleanup_real_data(tmp_path / "outside.json", repository_root=tmp_path)


def test_cleanup_validates_temporary_entries_before_deleting_artifacts(tmp_path: Path) -> None:
    run_path = publish_run_manifest(fake_shards(), context=CONTEXT, repository_root=tmp_path)
    shard = fake_shards()[0]
    artifact = tmp_path / Path(*shard.artifact_relative_path.split("/"))
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"synthetic")
    unsafe = tmp_path / "data" / "raw" / "cfpb" / ".tmp" / CONTEXT.run_id / "unexpected.txt"
    unsafe.parent.mkdir(parents=True)
    unsafe.write_text("synthetic")

    with pytest.raises(ExtractionError, match="unsafe_cleanup_temporary_entry"):
        cleanup_real_data(
            run_path,
            repository_root=tmp_path,
            execute=True,
            confirmation=CONTEXT.run_id,
        )

    assert artifact.exists()


def test_safe_error_does_not_include_response_body() -> None:
    report = safe_extraction_error(ExtractionError("export_json_invalid", month="2023-09"))
    assert report["privacy"] == {"source_values_logged": False, "response_body_logged": False}
