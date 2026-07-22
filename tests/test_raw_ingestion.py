import hashlib
import json
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from complaint_triage.raw_ingestion import (
    RawIngestionError,
    prepare_raw_batch,
    safe_ingestion_error,
)

REPOSITORY_ROOT = Path(__file__).parents[1]
MANIFEST_FIXTURE = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "cfpb" / "raw_batch_manifest_synthetic.json"
)
ARTIFACT_FIXTURE = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "cfpb" / "search_response_synthetic.json"
)


def stage_batch(tmp_path: Path) -> tuple[Path, dict]:
    manifest = json.loads(MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "data" / "manifests" / "cfpb" / "batch.json"
    artifact_path = tmp_path / Path(*Path(manifest["artifact"]["relative_path"]).parts)
    manifest_path.parent.mkdir(parents=True)
    artifact_path.parent.mkdir(parents=True)
    shutil.copyfile(MANIFEST_FIXTURE, manifest_path)
    shutil.copyfile(ARTIFACT_FIXTURE, artifact_path)
    return manifest_path, manifest


def test_valid_synthetic_batch_is_prepared_without_source_values_in_result(tmp_path: Path) -> None:
    manifest_path, _ = stage_batch(tmp_path)

    prepared = prepare_raw_batch(manifest_path, repository_root=tmp_path)

    assert len(prepared.records) == 3
    assert [record.ordinal for record in prepared.records] == [0, 1, 2]
    assert all(len(record.sha256) == 64 for record in prepared.records)


def test_manifest_must_be_in_the_controlled_repository_directory(tmp_path: Path) -> None:
    manifest_path, _ = stage_batch(tmp_path)
    unsafe_path = tmp_path / "batch.json"
    shutil.copyfile(manifest_path, unsafe_path)

    with pytest.raises(RawIngestionError) as raised:
        prepare_raw_batch(unsafe_path, repository_root=tmp_path)

    assert raised.value.code == "unsafe_manifest_path"


def test_changed_artifact_bytes_are_rejected_before_parsing(tmp_path: Path) -> None:
    manifest_path, manifest = stage_batch(tmp_path)
    artifact_path = tmp_path / Path(*Path(manifest["artifact"]["relative_path"]).parts)
    artifact_path.write_bytes(artifact_path.read_bytes() + b"\n")

    with pytest.raises(RawIngestionError) as raised:
        prepare_raw_batch(manifest_path, repository_root=tmp_path)

    assert raised.value.code == "artifact_checksum_mismatch"


def test_manifest_aggregate_drift_is_rejected_without_exposing_values(tmp_path: Path) -> None:
    manifest_path, manifest = stage_batch(tmp_path)
    changed = deepcopy(manifest)
    changed["records"]["returned_record_count"] = 2
    manifest_path.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(RawIngestionError) as raised:
        prepare_raw_batch(manifest_path, repository_root=tmp_path)

    assert raised.value.code == "record_reconciliation_failed"
    assert raised.value.details == {"field": "returned_record_count"}


def test_real_data_is_blocked_until_retention_policy_is_approved(tmp_path: Path) -> None:
    manifest_path, manifest = stage_batch(tmp_path)
    changed = deepcopy(manifest)
    changed["is_synthetic"] = False
    changed["privacy"]["retention_policy_id"] = "unapproved-example"
    manifest_path.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(RawIngestionError) as raised:
        prepare_raw_batch(manifest_path, repository_root=tmp_path)

    assert raised.value.code == "real_data_retention_policy_unapproved"


def test_artifact_cannot_exceed_manifest_request_limit(tmp_path: Path) -> None:
    manifest_path, manifest = stage_batch(tmp_path)
    changed = deepcopy(manifest)
    changed["request"]["parameters"]["size"] = "2"
    fingerprint_input = {
        "base_url": changed["request"]["base_url"],
        "endpoint_id": changed["source"]["endpoint_id"],
        "method": changed["request"]["method"],
        "parameters": changed["request"]["parameters"],
        "schema": changed["request"]["fingerprint_schema"],
    }
    fingerprint_bytes = json.dumps(
        fingerprint_input,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    changed["request"]["request_fingerprint_sha256"] = hashlib.sha256(fingerprint_bytes).hexdigest()
    manifest_path.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(RawIngestionError) as raised:
        prepare_raw_batch(manifest_path, repository_root=tmp_path)

    assert raised.value.code == "bounded_request_limit_exceeded"


def test_safe_error_never_contains_raw_narrative() -> None:
    narrative = json.loads(ARTIFACT_FIXTURE.read_text(encoding="utf-8"))["hits"]["hits"][0][
        "_source"
    ]["complaint_what_happened"]
    report = safe_ingestion_error(
        RawIngestionError("artifact_record_invalid", source_row_ordinal=0)
    )

    assert narrative not in json.dumps(report)
    assert report["privacy"]["raw_payload_logged"] is False
