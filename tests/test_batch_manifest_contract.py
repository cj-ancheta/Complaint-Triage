import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(__file__).parents[1] / "contracts" / "cfpb-raw-batch-manifest.schema.json"
MANIFEST_PATH = Path(__file__).parent / "fixtures" / "cfpb" / "raw_batch_manifest_synthetic.json"
RAW_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cfpb" / "search_response_synthetic.json"

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
BATCH_ID_PATTERN = re.compile(r"^cfpb-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_request_bytes(manifest: dict) -> bytes:
    request = manifest["request"]
    fingerprint_input = {
        "base_url": request["base_url"],
        "endpoint_id": manifest["source"]["endpoint_id"],
        "method": request["method"],
        "parameters": request["parameters"],
        "schema": request["fingerprint_schema"],
    }
    return json.dumps(
        fingerprint_input,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def test_manifest_schema_is_closed_and_versioned() -> None:
    schema = load_json(SCHEMA_PATH)

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["manifest_version"]["enum"] == ["1.0.0", "2.0.0"]
    assert schema["$defs"]["sha256"]["pattern"] == "^[0-9a-f]{64}$"

    for section in (
        "source",
        "request",
        "response",
        "artifact",
        "records",
        "schema_observation",
        "lineage",
        "privacy",
    ):
        assert schema["properties"][section]["additionalProperties"] is False


def test_synthetic_manifest_has_all_required_sections() -> None:
    schema = load_json(SCHEMA_PATH)
    manifest = load_json(MANIFEST_PATH)

    assert set(manifest) == set(schema["required"])
    assert manifest["manifest_version"] == "1.0.0"
    assert manifest["is_synthetic"] is True
    assert BATCH_ID_PATTERN.fullmatch(manifest["batch_id"])


def test_synthetic_manifest_validates_against_json_schema() -> None:
    schema = load_json(SCHEMA_PATH)
    manifest = load_json(MANIFEST_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    errors = sorted(validator.iter_errors(manifest), key=lambda error: list(error.path))

    assert errors == []


def test_schema_rejects_export_format_and_oversized_request() -> None:
    schema = load_json(SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    manifest_with_export = deepcopy(load_json(MANIFEST_PATH))
    manifest_with_export["request"]["parameters"]["format"] = "json"
    manifest_with_oversized_request = deepcopy(load_json(MANIFEST_PATH))
    manifest_with_oversized_request["request"]["parameters"]["size"] = "101"

    assert list(validator.iter_errors(manifest_with_export))
    assert list(validator.iter_errors(manifest_with_oversized_request))


def test_artifact_checksum_covers_exact_fixture_bytes() -> None:
    manifest = load_json(MANIFEST_PATH)
    raw_bytes = RAW_FIXTURE_PATH.read_bytes()
    checksum = hashlib.sha256(raw_bytes).hexdigest()
    artifact = manifest["artifact"]

    assert SHA256_PATTERN.fullmatch(checksum)
    assert artifact["hash_algorithm"] == "SHA-256"
    assert artifact["hash_scope"] == "stored_bytes"
    assert artifact["sha256"] == checksum
    assert artifact["byte_count"] == len(raw_bytes)
    assert artifact["relative_path"] == f"data/raw/cfpb/sha256/{checksum[:2]}/{checksum}.json"


def test_request_fingerprint_uses_canonical_json() -> None:
    manifest = load_json(MANIFEST_PATH)
    expected = hashlib.sha256(canonical_request_bytes(manifest)).hexdigest()

    assert manifest["request"]["request_fingerprint_sha256"] == expected


def test_batch_id_combines_retrieval_time_and_artifact_prefix() -> None:
    manifest = load_json(MANIFEST_PATH)
    compact_timestamp = manifest["response"]["retrieved_at_utc"].replace("-", "").replace(":", "")
    expected = f"cfpb-{compact_timestamp}-{manifest['artifact']['sha256'][:12]}"

    assert manifest["batch_id"] == expected


def test_manifest_counts_reconcile_with_synthetic_fixture() -> None:
    manifest = load_json(MANIFEST_PATH)
    response = load_json(RAW_FIXTURE_PATH)
    sources = [hit["_source"] for hit in response["hits"]["hits"]]
    complaint_ids = [source["complaint_id"] for source in sources]
    records = manifest["records"]

    assert records["returned_record_count"] == len(sources)
    assert records["matching_total"] == response["hits"]["total"]["value"]
    assert records["unique_complaint_id_count"] == len(set(complaint_ids))
    assert records["duplicate_complaint_id_count"] == len(complaint_ids) - len(set(complaint_ids))
    assert records["non_empty_narrative_count"] == sum(
        bool(source["complaint_what_happened"].strip()) for source in sources
    )
    assert records["returned_record_count"] <= int(manifest["request"]["parameters"]["size"])
    assert (
        records["unique_complaint_id_count"] + records["duplicate_complaint_id_count"]
        == records["returned_record_count"]
    )
    assert records["non_empty_narrative_count"] <= records["returned_record_count"]
    assert manifest["schema_observation"]["source_fields"] == sorted(sources[0])


def test_manifest_contains_no_individual_source_values() -> None:
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")
    response = load_json(RAW_FIXTURE_PATH)

    for hit in response["hits"]["hits"]:
        source = hit["_source"]
        assert source["complaint_what_happened"] not in manifest_text
        assert source["company"] not in manifest_text
        assert source["complaint_id"] not in manifest_text
        assert source["product"] not in manifest_text


def test_manifest_uses_only_relative_posix_artifact_path() -> None:
    relative_path = PurePosixPath(load_json(MANIFEST_PATH)["artifact"]["relative_path"])

    assert not relative_path.is_absolute()
    assert ".." not in relative_path.parts
    assert relative_path.parts[:4] == ("data", "raw", "cfpb", "sha256")


def test_repository_ignores_raw_artifacts_but_not_safe_manifests() -> None:
    ignore_lines = {
        line.strip()
        for line in (Path(__file__).parents[1] / ".gitignore")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "data/raw/" in ignore_lines
    assert "data/manifests/" not in ignore_lines
