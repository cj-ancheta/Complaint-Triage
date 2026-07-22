import copy
import json
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from complaint_triage.taxonomy_profile import (
    CFPB_TAXONOMY_PROFILE_URL,
    CURRENT_PRODUCT_LABELS,
    MAX_RESPONSE_BYTES,
    TaxonomyProfileError,
    build_safe_taxonomy_profile,
    fetch_taxonomy_profile,
    safe_taxonomy_error_report,
    validate_taxonomy_profile_url,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cfpb" / "taxonomy_trends_synthetic.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        self.body = body
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.read_amounts: list[int | None] = []

    def read(self, amount: int | None = None) -> bytes:
        self.read_amounts.append(amount)
        return self.body if amount is None else self.body[:amount]

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeOpener:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.requests = []
        self.timeouts: list[float] = []

    def open(self, request, timeout: float) -> FakeResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        return self.response


def test_fixed_request_is_aggregate_only_and_spans_transition() -> None:
    validate_taxonomy_profile_url(CFPB_TAXONOMY_PROFILE_URL)
    parts = urlsplit(CFPB_TAXONOMY_PROFILE_URL)
    query = parse_qs(parts.query)

    assert parts.scheme == "https"
    assert parts.hostname == "www.consumerfinance.gov"
    assert parts.path.endswith("/trends")
    assert query["has_narrative"] == ["true"]
    assert query["lens"] == ["overview"]
    assert query["date_received_min"] == ["2023-07-01"]
    assert query["date_received_max"] == ["2025-01-01"]
    assert "format" not in query
    assert "size" not in query
    assert "search_term" not in query


@pytest.mark.parametrize(
    "unsafe_url",
    [
        CFPB_TAXONOMY_PROFILE_URL.replace("https://", "http://"),
        CFPB_TAXONOMY_PROFILE_URL.replace("www.consumerfinance.gov", "example.com"),
        f"{CFPB_TAXONOMY_PROFILE_URL}&format=json",
        f"{CFPB_TAXONOMY_PROFILE_URL}&size=1",
        f"{CFPB_TAXONOMY_PROFILE_URL}&no_aggs=true",
        CFPB_TAXONOMY_PROFILE_URL.replace("has_narrative=true", "has_narrative=false"),
        CFPB_TAXONOMY_PROFILE_URL.replace("2023-07-01", "2023-01-01"),
    ],
)
def test_request_boundary_rejects_any_change(unsafe_url: str) -> None:
    with pytest.raises(TaxonomyProfileError, match="unsafe_request"):
        validate_taxonomy_profile_url(unsafe_url)


def test_profile_separates_transition_and_candidate_labels() -> None:
    report = build_safe_taxonomy_profile(
        load_fixture(),
        requested_at_utc="2026-07-22T08:00:00+00:00",
        elapsed_ms=12.3456,
        response_bytes=1234,
        content_type="application/json",
    )

    assert report["status"] == "ok"
    assert report["request"]["complaint_rows_requested"] == 0
    assert report["candidate_window"]["date_received_min"] == "2023-09-01"
    assert report["candidate_window"]["date_received_max_exclusive"] == "2025-01-01"
    assert report["observed"]["transition_labels"] == ["Credit card or prepaid card"]
    assert report["candidate_window"]["legacy_labels_observed"] == []
    assert report["candidate_window"]["unexpected_labels_observed"] == []
    assert report["candidate_window"]["counts_by_product"] == {
        "Credit card": 4,
        "Debt collection": 5,
        "Debt or credit management": 2,
    }
    assert set(report["candidate_window"]["current_labels_without_observed_rows"]) == (
        CURRENT_PRODUCT_LABELS - {"Credit card", "Debt collection", "Debt or credit management"}
    )
    assert report["checks"]["product_counts_reconcile"] is True
    assert report["checks"]["candidate_months_complete"] is False
    assert report["checks"]["product_monthly_counts_reconcile"] is True
    assert report["privacy"]["narratives_received"] is False


def test_product_monthly_counts_must_reconcile_to_bucket_total() -> None:
    fixture = load_fixture()
    fixture["aggregations"]["product"]["product"]["buckets"][1]["doc_count"] += 1

    with pytest.raises(TaxonomyProfileError) as raised:
        build_safe_taxonomy_profile(
            fixture,
            requested_at_utc="2026-07-22T08:00:00+00:00",
            elapsed_ms=1,
            response_bytes=100,
            content_type="application/json",
        )

    assert raised.value.code == "product_trend_reconciliation_failed"


def test_legacy_label_after_candidate_start_is_reported() -> None:
    fixture = copy.deepcopy(load_fixture())
    legacy_bucket = fixture["aggregations"]["product"]["product"]["buckets"][0]
    legacy_bucket["trend_period"]["buckets"][1]["key_as_string"] = "2023-09-01T00:00:00.000Z"

    report = build_safe_taxonomy_profile(
        fixture,
        requested_at_utc="2026-07-22T08:00:00+00:00",
        elapsed_ms=1,
        response_bytes=100,
        content_type="application/json",
    )

    assert report["candidate_window"]["legacy_labels_observed"] == ["Credit card or prepaid card"]
    assert report["checks"]["no_legacy_labels_in_candidate_window"] is False


def test_incomplete_product_aggregation_is_rejected() -> None:
    fixture = load_fixture()
    fixture["aggregations"]["product"]["product"]["sum_other_doc_count"] = 1

    with pytest.raises(TaxonomyProfileError) as raised:
        build_safe_taxonomy_profile(
            fixture,
            requested_at_utc="2026-07-22T08:00:00+00:00",
            elapsed_ms=1,
            response_bytes=100,
            content_type="application/json",
        )

    assert raised.value.code == "incomplete_product_aggregation"
    assert raised.value.safe_details == {"omitted_record_count": 1}


def test_response_with_complaint_hits_is_rejected_without_inspecting_values() -> None:
    fixture = load_fixture()
    fixture["hits"] = {"hits": [{"_source": {"complaint_what_happened": "private"}}]}

    with pytest.raises(TaxonomyProfileError) as raised:
        build_safe_taxonomy_profile(
            fixture,
            requested_at_utc="2026-07-22T08:00:00+00:00",
            elapsed_ms=1,
            response_bytes=100,
            content_type="application/json",
        )

    assert raised.value.code == "unexpected_complaint_rows"
    assert raised.value.safe_details == {"returned_row_count": 1}
    report = safe_taxonomy_error_report(raised.value)
    assert report["privacy"]["complaint_rows_received"] is True
    assert report["privacy"]["narratives_received"] is None
    assert report["privacy"]["narrative_fields_inspected"] is False


def test_fetch_reads_only_bounded_aggregate_json() -> None:
    body = json.dumps(load_fixture()).encode("utf-8")
    response = FakeResponse(body)
    opener = FakeOpener(response)
    clock_values = iter([10.0, 10.025])

    report = fetch_taxonomy_profile(
        opener=opener,
        requested_at_utc="2026-07-22T08:00:00+00:00",
        clock=lambda: next(clock_values),
    )

    assert report["http"]["elapsed_ms"] == 25.0
    assert response.read_amounts == [MAX_RESPONSE_BYTES + 1]
    assert opener.requests[0].full_url == CFPB_TAXONOMY_PROFILE_URL
    assert opener.requests[0].headers["Accept"] == "application/json"


def test_safe_error_contains_no_response_body() -> None:
    report = safe_taxonomy_error_report(
        TaxonomyProfileError(
            "http_error",
            requested_at_utc="2026-07-22T08:00:00+00:00",
            http_status=403,
        )
    )

    assert report["error"]["code"] == "http_error"
    assert report["error"]["http_status"] == 403
    assert report["privacy"]["response_body_logged"] is False
    assert report["privacy"]["narratives_received"] is False
