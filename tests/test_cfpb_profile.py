import copy
import io
import json
from email.message import Message
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

import pytest

from complaint_triage import cfpb_profile
from complaint_triage.cfpb_profile import (
    CFPB_PROFILE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
    NoRedirectHandler,
    ProfileError,
    build_safe_profile,
    fetch_cfpb_profile,
    safe_error_report,
    validate_profile_url,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cfpb" / "search_response_synthetic.json"


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
    def __init__(
        self, response: FakeResponse | None = None, error: Exception | None = None
    ) -> None:
        self.response = response
        self.error = error
        self.requests = []
        self.timeouts: list[float] = []

    def open(self, request, timeout: float) -> FakeResponse:
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def test_pinned_url_has_the_approved_boundary() -> None:
    validate_profile_url(CFPB_PROFILE_URL)
    parts = urlsplit(CFPB_PROFILE_URL)
    query = parse_qs(parts.query)

    assert parts.scheme == "https"
    assert parts.hostname == "www.consumerfinance.gov"
    assert query["size"] == ["5"]
    assert query["no_aggs"] == ["true"]
    assert query["no_highlight"] == ["true"]
    assert "format" not in query


@pytest.mark.parametrize(
    "unsafe_url",
    [
        CFPB_PROFILE_URL.replace("https://", "http://"),
        CFPB_PROFILE_URL.replace("www.consumerfinance.gov", "example.com"),
        f"{CFPB_PROFILE_URL}&format=json",
        CFPB_PROFILE_URL.replace("size=5", "size=6"),
        CFPB_PROFILE_URL.replace("date_received_max=2024-01-03", "date_received_max=2024-02-03"),
    ],
)
def test_request_boundary_rejects_any_unapproved_change(unsafe_url: str) -> None:
    with pytest.raises(ProfileError, match="unsafe_request"):
        validate_profile_url(unsafe_url)


def test_redirect_handler_rejects_redirects() -> None:
    handler = NoRedirectHandler()
    request = Request(CFPB_PROFILE_URL)

    assert (
        handler.redirect_request(
            request,
            fp=None,
            code=302,
            msg="Found",
            headers=Message(),
            newurl="https://example.com/",
        )
        is None
    )
    assert request.full_url == CFPB_PROFILE_URL


def test_safe_profile_reports_schema_without_individual_values() -> None:
    fixture = load_fixture()
    report = build_safe_profile(
        fixture,
        requested_at_utc="2026-07-21T05:00:00+00:00",
        elapsed_ms=12.3456,
        response_bytes=1234,
        content_type="application/json",
    )
    serialized = json.dumps(report)

    assert report["status"] == "ok"
    assert report["result"]["returned_hit_count"] == 3
    assert report["narratives"]["present_count"] == 3
    assert report["http"]["elapsed_ms"] == 12.346
    assert report["privacy"]["source_values_logged"] is False

    for hit in fixture["hits"]["hits"]:
        source = hit["_source"]
        assert source["complaint_what_happened"] not in serialized
        assert source["company"] not in serialized
        assert source["complaint_id"] not in serialized
        assert source["product"] not in serialized


def test_safe_profile_reports_additive_fields_without_their_values() -> None:
    fixture = load_fixture()
    fixture["hits"]["hits"][0]["_source"]["new_source_field"] = "PRIVATE VALUE"

    report = build_safe_profile(
        fixture,
        requested_at_utc="2026-07-21T05:00:00+00:00",
        elapsed_ms=1,
        response_bytes=100,
        content_type="application/json",
    )

    assert report["schema"]["unexpected_fields"] == ["new_source_field"]
    assert report["schema"]["field_observations"]["new_source_field"] == {
        "null_count": 2,
        "types": ["null", "string"],
    }
    assert "PRIVATE VALUE" not in json.dumps(report)


def test_safe_profile_does_not_emit_pagination_break_points() -> None:
    fixture = load_fixture()
    fixture["_meta"]["break_points"] = {"2": [1704153600000, "PRIVATE COMPLAINT ID"]}

    report = build_safe_profile(
        fixture,
        requested_at_utc="2026-07-21T05:00:00+00:00",
        elapsed_ms=1,
        response_bytes=100,
        content_type="application/json",
    )

    assert "break_points" not in report["source_meta"]
    assert "PRIVATE COMPLAINT ID" not in json.dumps(report)


def test_missing_source_field_fails_with_field_names_only() -> None:
    fixture = load_fixture()
    private_narrative = fixture["hits"]["hits"][0]["_source"].pop("complaint_what_happened")

    with pytest.raises(ProfileError) as captured:
        build_safe_profile(
            fixture,
            requested_at_utc="2026-07-21T05:00:00+00:00",
            elapsed_ms=1,
            response_bytes=100,
            content_type="application/json",
        )

    report = safe_error_report(captured.value)
    assert report["error"] == {
        "code": "source_schema_missing_fields",
        "missing_fields": ["complaint_what_happened"],
    }
    assert private_narrative not in json.dumps(report)


def test_more_than_five_hits_is_rejected() -> None:
    fixture = load_fixture()
    fixture["hits"]["hits"] = [copy.deepcopy(fixture["hits"]["hits"][0]) for _ in range(6)]

    with pytest.raises(ProfileError, match="response_hit_limit_exceeded"):
        build_safe_profile(
            fixture,
            requested_at_utc="2026-07-21T05:00:00+00:00",
            elapsed_ms=1,
            response_bytes=100,
            content_type="application/json",
        )


def test_empty_hit_list_cannot_claim_the_source_contract_is_valid() -> None:
    fixture = load_fixture()
    fixture["hits"]["hits"] = []
    fixture["hits"]["total"] = {"relation": "eq", "value": 0}

    with pytest.raises(ProfileError, match="empty_profile_result"):
        build_safe_profile(
            fixture,
            requested_at_utc="2026-07-21T05:00:00+00:00",
            elapsed_ms=1,
            response_bytes=100,
            content_type="application/json",
        )


@pytest.mark.parametrize(
    ("field", "value", "expected_check"),
    [
        ("has_narrative", False, "has_narrative_is_true"),
        ("complaint_what_happened", "   ", "narrative_is_non_empty_string"),
    ],
)
def test_narrative_contract_failures_are_structural_only(
    field: str,
    value: object,
    expected_check: str,
) -> None:
    fixture = load_fixture()
    fixture["hits"]["hits"][0]["_source"][field] = value

    with pytest.raises(ProfileError) as captured:
        build_safe_profile(
            fixture,
            requested_at_utc="2026-07-21T05:00:00+00:00",
            elapsed_ms=1,
            response_bytes=100,
            content_type="application/json",
        )

    assert captured.value.code == "source_contract_check_failed"
    assert captured.value.safe_details == {"failed_checks": [expected_check]}


def test_fetch_makes_one_bounded_request_and_returns_safe_profile() -> None:
    body = json.dumps(load_fixture()).encode()
    response = FakeResponse(body)
    opener = FakeOpener(response)
    times = iter([100.0, 100.025])

    report = fetch_cfpb_profile(
        opener=opener,
        requested_at_utc="2026-07-21T05:00:00+00:00",
        clock=lambda: next(times),
    )

    assert len(opener.requests) == 1
    assert opener.timeouts == [DEFAULT_TIMEOUT_SECONDS]
    assert opener.requests[0].full_url == CFPB_PROFILE_URL
    assert opener.requests[0].get_header("Accept") == "application/json"
    assert response.read_amounts == [MAX_RESPONSE_BYTES + 1]
    assert report["http"]["elapsed_ms"] == 25.0


def test_non_json_response_is_not_read() -> None:
    response = FakeResponse(b"SENSITIVE NARRATIVE", content_type="text/html")

    with pytest.raises(ProfileError, match="unexpected_content_type"):
        fetch_cfpb_profile(
            opener=FakeOpener(response),
            requested_at_utc="2026-07-21T05:00:00+00:00",
        )

    assert response.read_amounts == []


def test_response_byte_limit_stops_before_json_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfpb_profile, "MAX_RESPONSE_BYTES", 10)
    response = FakeResponse(b"SENSITIVE NARRATIVE")

    with pytest.raises(ProfileError) as captured:
        fetch_cfpb_profile(
            opener=FakeOpener(response),
            requested_at_utc="2026-07-21T05:00:00+00:00",
        )

    assert captured.value.code == "response_byte_limit_exceeded"
    assert "SENSITIVE NARRATIVE" not in json.dumps(safe_error_report(captured.value))


def test_invalid_json_error_does_not_include_response_content() -> None:
    private_body = b'{"narrative": "SENSITIVE NARRATIVE"'

    with pytest.raises(ProfileError) as captured:
        fetch_cfpb_profile(
            opener=FakeOpener(FakeResponse(private_body)),
            requested_at_utc="2026-07-21T05:00:00+00:00",
        )

    assert captured.value.code == "invalid_json_response"
    assert "SENSITIVE NARRATIVE" not in json.dumps(safe_error_report(captured.value))


def test_http_error_body_is_not_read_or_reported() -> None:
    private_body = io.BytesIO(b"SENSITIVE NARRATIVE")
    headers = Message()
    headers["Content-Type"] = "text/html"
    error = HTTPError(CFPB_PROFILE_URL, 403, "Forbidden", headers, private_body)

    with pytest.raises(ProfileError) as captured:
        fetch_cfpb_profile(
            opener=FakeOpener(error=error),
            requested_at_utc="2026-07-21T05:00:00+00:00",
        )

    report = safe_error_report(captured.value)
    assert private_body.tell() == 0
    assert report["error"]["http_status"] == 403
    assert "SENSITIVE NARRATIVE" not in json.dumps(report)
