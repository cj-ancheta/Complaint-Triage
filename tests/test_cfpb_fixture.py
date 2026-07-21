import json
from pathlib import Path

EXPECTED_SOURCE_FIELDS = {
    "company",
    "company_public_response",
    "company_response",
    "complaint_id",
    "complaint_what_happened",
    "date_received",
    "date_sent_to_company",
    "has_narrative",
    "issue",
    "product",
    "state",
    "submitted_via",
    "sub_issue",
    "sub_product",
    "tags",
    "timely",
    "zip_code",
}

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cfpb" / "search_response_synthetic.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_synthetic_fixture_matches_bounded_source_contract() -> None:
    response = load_fixture()
    hits = response["hits"]["hits"]

    assert 0 < len(hits) <= 5
    assert response["hits"]["total"] == {"relation": "eq", "value": len(hits)}

    for hit in hits:
        source = hit["_source"]
        assert set(source) == EXPECTED_SOURCE_FIELDS
        assert source["has_narrative"] is True
        assert source["complaint_what_happened"].startswith("SYNTHETIC TEST RECORD")
        assert source["company"].startswith("SYNTHETIC")
        assert source["complaint_id"].startswith("SYN-")
        assert source["product"].startswith("SYNTHETIC_PRODUCT_")


def test_synthetic_fixture_exercises_nullable_fields_and_utf8() -> None:
    sources = [hit["_source"] for hit in load_fixture()["hits"]["hits"]]

    assert any(value is None for source in sources for value in source.values())
    assert any("—" in source["complaint_what_happened"] for source in sources)
