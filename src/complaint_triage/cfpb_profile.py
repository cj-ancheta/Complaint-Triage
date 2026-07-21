"""Privacy-safe, bounded profiling for the CFPB complaint search API."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from time import perf_counter
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

CFPB_PROFILE_URL = (
    "https://www.consumerfinance.gov/data-research/consumer-complaints/"
    "search/api/v1/?date_received_min=2024-01-02&date_received_max=2024-01-03"
    "&has_narrative=true&no_aggs=true&no_highlight=true&size=5"
    "&sort=created_date_desc"
)
CFPB_HOST = "www.consumerfinance.gov"
CFPB_PATH = "/data-research/consumer-complaints/search/api/v1/"
MAX_HITS = 5
MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_TIMEOUT_SECONDS = 10.0
USER_AGENT = "complaint-triage-contract-check/0.1"

EXPECTED_QUERY = {
    "date_received_max": ["2024-01-03"],
    "date_received_min": ["2024-01-02"],
    "has_narrative": ["true"],
    "no_aggs": ["true"],
    "no_highlight": ["true"],
    "size": ["5"],
    "sort": ["created_date_desc"],
}

EXPECTED_SOURCE_FIELDS = frozenset(
    {
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
)

SAFE_META_FIELDS = (
    "has_data_issue",
    "is_data_stale",
    "is_narrative_stale",
    "last_indexed",
    "last_updated",
    "license",
    "total_record_count",
)


class ResponseLike(Protocol):
    """The small part of an HTTP response used by this module."""

    status: int
    headers: Any

    def read(self, amount: int | None = None) -> bytes: ...

    def __enter__(self) -> ResponseLike: ...

    def __exit__(self, *args: object) -> None: ...


class OpenerLike(Protocol):
    """Protocol that permits a deterministic fake transport in tests."""

    def open(self, request: Request, timeout: float) -> ResponseLike: ...


class ProfileError(RuntimeError):
    """A profiling failure containing only values that are safe to display."""

    def __init__(self, code: str, **safe_details: object) -> None:
        super().__init__(code)
        self.code = code
        self.safe_details = safe_details


class NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so the fixed host boundary cannot change silently."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def validate_profile_url(url: str) -> None:
    """Validate the fixed CT-102 request before any network access occurs."""

    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != CFPB_HOST
        or parts.path != CFPB_PATH
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
    ):
        raise ProfileError("unsafe_request_boundary")

    try:
        port = parts.port
    except ValueError as error:
        raise ProfileError("unsafe_request_boundary") from error
    if port not in (None, 443):
        raise ProfileError("unsafe_request_boundary")

    query = parse_qs(parts.query, keep_blank_values=True)
    if query != EXPECTED_QUERY or "format" in query:
        raise ProfileError("unsafe_request_parameters")

    try:
        lower = date.fromisoformat(query["date_received_min"][0])
        upper = date.fromisoformat(query["date_received_max"][0])
        size = int(query["size"][0])
    except (KeyError, ValueError) as error:
        raise ProfileError("unsafe_request_parameters") from error

    if (upper - lower).days != 1 or not 1 <= size <= MAX_HITS:
        raise ProfileError("unsafe_request_parameters")


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _require_mapping(value: object, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ProfileError("invalid_response_shape", location=location)
    return value


def build_safe_profile(
    payload: object,
    *,
    requested_at_utc: str,
    elapsed_ms: float,
    response_bytes: int,
    content_type: str,
) -> dict[str, object]:
    """Derive a schema profile without returning individual source values."""

    root = _require_mapping(payload, "root")
    meta = _require_mapping(root.get("_meta"), "_meta")
    hits_object = _require_mapping(root.get("hits"), "hits")
    total = _require_mapping(hits_object.get("total"), "hits.total")
    hits = hits_object.get("hits")

    if not isinstance(hits, list):
        raise ProfileError("invalid_response_shape", location="hits.hits")
    if not hits:
        raise ProfileError("empty_profile_result")
    if len(hits) > MAX_HITS:
        raise ProfileError(
            "response_hit_limit_exceeded",
            returned_hit_count=len(hits),
            approved_hit_limit=MAX_HITS,
        )
    if type(total.get("value")) is not int or not isinstance(total.get("relation"), str):
        raise ProfileError("invalid_response_shape", location="hits.total")

    sources: list[Mapping[str, Any]] = []
    for hit in hits:
        hit_object = _require_mapping(hit, "hits.hits[]")
        sources.append(_require_mapping(hit_object.get("_source"), "hits.hits[]._source"))

    observed_fields = set().union(*(set(source) for source in sources))
    fields_missing_from_any_hit = set().union(
        *(EXPECTED_SOURCE_FIELDS - set(source) for source in sources)
    )
    if fields_missing_from_any_hit:
        raise ProfileError(
            "source_schema_missing_fields",
            missing_fields=sorted(fields_missing_from_any_hit),
        )

    narrative_lengths: list[int] = []
    failed_checks: set[str] = set()
    for source in sources:
        narrative = source["complaint_what_happened"]
        if not isinstance(narrative, str) or not narrative.strip():
            failed_checks.add("narrative_is_non_empty_string")
        else:
            narrative_lengths.append(len(narrative))
        if source["has_narrative"] is not True:
            failed_checks.add("has_narrative_is_true")

    if failed_checks:
        raise ProfileError("source_contract_check_failed", failed_checks=sorted(failed_checks))

    field_observations: dict[str, dict[str, object]] = {}
    for field in sorted(observed_fields):
        values = [source.get(field) for source in sources]
        field_observations[field] = {
            "null_count": sum(value is None for value in values),
            "types": sorted({_json_type(value) for value in values}),
        }

    source_meta = {field: meta.get(field) for field in SAFE_META_FIELDS}
    unexpected_fields = observed_fields - EXPECTED_SOURCE_FIELDS

    return {
        "status": "ok",
        "request": {
            "endpoint": "cfpb_complaint_search_v1",
            "requested_at_utc": requested_at_utc,
            "date_received_min": EXPECTED_QUERY["date_received_min"][0],
            "date_received_max": EXPECTED_QUERY["date_received_max"][0],
            "requested_hit_limit": MAX_HITS,
        },
        "http": {
            "status": 200,
            "content_type": content_type,
            "elapsed_ms": round(elapsed_ms, 3),
            "response_bytes": response_bytes,
        },
        "source_meta": source_meta,
        "result": {
            "matching_total": total["value"],
            "matching_total_relation": total["relation"],
            "returned_hit_count": len(hits),
        },
        "schema": {
            "expected_fields": sorted(EXPECTED_SOURCE_FIELDS),
            "observed_fields": sorted(observed_fields),
            "missing_fields": [],
            "unexpected_fields": sorted(unexpected_fields),
            "field_observations": field_observations,
        },
        "narratives": {
            "present_count": len(narrative_lengths),
            "minimum_length": min(narrative_lengths),
            "maximum_length": max(narrative_lengths),
        },
        "privacy": {
            "response_body_logged": False,
            "source_values_logged": False,
            "response_persisted": False,
        },
        "checks": {
            "returned_hits_lte_5": len(hits) <= MAX_HITS,
            "all_hits_have_expected_fields": True,
            "all_hits_have_narratives": len(narrative_lengths) == len(hits),
            "all_has_narrative_values_true": True,
        },
    }


def _content_type(headers: Any) -> str:
    get_content_type = getattr(headers, "get_content_type", None)
    if callable(get_content_type):
        return str(get_content_type()).lower()
    value = headers.get("Content-Type", "") if hasattr(headers, "get") else ""
    return str(value).split(";", maxsplit=1)[0].strip().lower()


def fetch_cfpb_profile(
    *,
    url: str = CFPB_PROFILE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    opener: OpenerLike | None = None,
    requested_at_utc: str | None = None,
    clock: Callable[[], float] = perf_counter,
) -> dict[str, object]:
    """Make one bounded request and return only a privacy-safe profile."""

    validate_profile_url(url)
    request_timestamp = requested_at_utc or datetime.now(UTC).isoformat()
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    transport = opener or build_opener(NoRedirectHandler())
    started = clock()

    try:
        with transport.open(request, timeout=timeout_seconds) as response:
            status = response.status
            content_type = _content_type(response.headers)
            if status != 200:
                raise ProfileError(
                    "http_error",
                    requested_at_utc=request_timestamp,
                    http_status=status,
                    content_type=content_type,
                )
            if content_type != "application/json" and not content_type.endswith("+json"):
                raise ProfileError(
                    "unexpected_content_type",
                    requested_at_utc=request_timestamp,
                    http_status=status,
                    content_type=content_type,
                )

            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ProfileError(
                    "response_byte_limit_exceeded",
                    requested_at_utc=request_timestamp,
                    approved_byte_limit=MAX_RESPONSE_BYTES,
                )

        elapsed_ms = (clock() - started) * 1000
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProfileError(
                "invalid_json_response",
                requested_at_utc=request_timestamp,
                http_status=200,
                content_type=content_type,
            ) from error

        return build_safe_profile(
            payload,
            requested_at_utc=request_timestamp,
            elapsed_ms=elapsed_ms,
            response_bytes=len(raw),
            content_type=content_type,
        )
    except ProfileError:
        raise
    except HTTPError as error:
        raise ProfileError(
            "http_error",
            requested_at_utc=request_timestamp,
            http_status=error.code,
            content_type=_content_type(error.headers),
        ) from None
    except (TimeoutError, URLError):
        raise ProfileError(
            "network_error",
            requested_at_utc=request_timestamp,
        ) from None


def safe_error_report(error: ProfileError) -> dict[str, object]:
    """Convert a controlled failure to output that cannot contain a response body."""

    return {
        "status": "error",
        "error": {"code": error.code, **error.safe_details},
        "privacy": {
            "response_body_logged": False,
            "source_values_logged": False,
            "response_persisted": False,
        },
    }
