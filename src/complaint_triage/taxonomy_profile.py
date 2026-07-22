"""Privacy-safe aggregate profiling for CFPB product-taxonomy stability."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from time import perf_counter
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

CFPB_TAXONOMY_PROFILE_URL = (
    "https://www.consumerfinance.gov/data-research/consumer-complaints/"
    "search/api/v1/trends?date_received_min=2023-07-01&date_received_max=2025-01-01"
    "&has_narrative=true&lens=overview&trend_depth=100&trend_interval=month"
)
CFPB_HOST = "www.consumerfinance.gov"
CFPB_TRENDS_PATH = "/data-research/consumer-complaints/search/api/v1/trends"
MAX_RESPONSE_BYTES = 3_000_000
DEFAULT_TIMEOUT_SECONDS = 20.0
USER_AGENT = "complaint-triage-taxonomy-profile/0.1"
TAXONOMY_EFFECTIVE_DATE = "2023-08-24"
CANDIDATE_WINDOW_START = "2023-09-01"
CANDIDATE_WINDOW_END_EXCLUSIVE = "2025-01-01"

EXPECTED_QUERY = {
    "date_received_max": ["2025-01-01"],
    "date_received_min": ["2023-07-01"],
    "has_narrative": ["true"],
    "lens": ["overview"],
    "trend_depth": ["100"],
    "trend_interval": ["month"],
}

CURRENT_PRODUCT_LABELS = frozenset(
    {
        "Checking or savings account",
        "Credit card",
        "Credit reporting or other personal consumer reports",
        "Debt collection",
        "Debt or credit management",
        "Money transfer, virtual currency, or money service",
        "Mortgage",
        "Payday loan, title loan, personal loan, or advance loan",
        "Prepaid card",
        "Student loan",
        "Vehicle loan or lease",
    }
)

LEGACY_CHANGED_PRODUCT_LABELS = frozenset(
    {
        "Credit card or prepaid card",
        "Credit reporting, credit repair services, or other personal consumer reports",
        "Payday loan, title loan, or personal loan",
    }
)


class ResponseLike(Protocol):
    status: int
    headers: Any

    def read(self, amount: int | None = None) -> bytes: ...

    def __enter__(self) -> ResponseLike: ...

    def __exit__(self, *args: object) -> None: ...


class OpenerLike(Protocol):
    def open(self, request: Request, timeout: float) -> ResponseLike: ...


class TaxonomyProfileError(RuntimeError):
    """A controlled aggregate-profile failure containing no complaint values."""

    def __init__(self, code: str, **safe_details: object) -> None:
        super().__init__(code)
        self.code = code
        self.safe_details = safe_details


class NoRedirectHandler(HTTPRedirectHandler):
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


def validate_taxonomy_profile_url(url: str) -> None:
    """Fail closed if the aggregate-only CT-201 request changes."""

    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != CFPB_HOST
        or parts.path != CFPB_TRENDS_PATH
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
    ):
        raise TaxonomyProfileError("unsafe_request_boundary")
    try:
        port = parts.port
    except ValueError as error:
        raise TaxonomyProfileError("unsafe_request_boundary") from error
    if port not in (None, 443):
        raise TaxonomyProfileError("unsafe_request_boundary")

    query = parse_qs(parts.query, keep_blank_values=True)
    forbidden_parameters = {"format", "frm", "no_aggs", "search_term", "size"}
    if query != EXPECTED_QUERY or forbidden_parameters & query.keys():
        raise TaxonomyProfileError("unsafe_request_parameters")


def build_safe_taxonomy_profile(
    payload: object,
    *,
    requested_at_utc: str,
    elapsed_ms: float,
    response_bytes: int,
    content_type: str,
) -> dict[str, object]:
    """Derive label/month counts from an aggregate response with no complaint hits."""

    root = _require_mapping(payload, "root")
    _assert_no_complaint_hits(root)
    aggregations = _require_mapping(root.get("aggregations"), "aggregations")
    product_aggregation = _require_mapping(aggregations.get("product"), "aggregations.product")
    product_terms = _require_mapping(
        product_aggregation.get("product"), "aggregations.product.product"
    )
    product_buckets = _require_list(
        product_terms.get("buckets"), "aggregations.product.product.buckets"
    )
    sum_other = _require_int(
        product_terms.get("sum_other_doc_count"),
        "aggregations.product.product.sum_other_doc_count",
    )
    if sum_other != 0:
        raise TaxonomyProfileError(
            "incomplete_product_aggregation",
            omitted_record_count=sum_other,
        )

    date_range = _require_mapping(
        aggregations.get("dateRangeBuckets"), "aggregations.dateRangeBuckets"
    )
    date_histogram = _require_mapping(
        date_range.get("dateRangeBuckets"),
        "aggregations.dateRangeBuckets.dateRangeBuckets",
    )
    date_buckets = _require_list(
        date_histogram.get("buckets"),
        "aggregations.dateRangeBuckets.dateRangeBuckets.buckets",
    )

    product_summaries: list[dict[str, object]] = []
    candidate_counts: dict[str, int] = {}
    observed_candidate_labels: set[str] = set()
    observed_transition_labels: set[str] = set()
    filtered_monthly_counts: dict[str, int] = {}
    product_total = 0

    for index, raw_bucket in enumerate(product_buckets):
        bucket = _require_mapping(raw_bucket, f"product_bucket[{index}]")
        label = bucket.get("key")
        count = bucket.get("doc_count")
        if not isinstance(label, str) or not label or type(count) is not int or count < 0:
            raise TaxonomyProfileError(
                "invalid_response_shape", location=f"product_bucket[{index}]"
            )
        trend = _require_mapping(
            bucket.get("trend_period"), f"product_bucket[{index}].trend_period"
        )
        months = _require_list(
            trend.get("buckets"), f"product_bucket[{index}].trend_period.buckets"
        )
        monthly_counts: dict[str, int] = {}
        for month_index, raw_month in enumerate(months):
            month_bucket = _require_mapping(
                raw_month,
                f"product_bucket[{index}].trend_period.buckets[{month_index}]",
            )
            month = _month_value(month_bucket, f"product_bucket[{index}].month[{month_index}]")
            month_count = _require_int(
                month_bucket.get("doc_count"),
                f"product_bucket[{index}].month[{month_index}].doc_count",
            )
            monthly_counts[month] = month_count
            filtered_monthly_counts[month] = filtered_monthly_counts.get(month, 0) + month_count
            if month < CANDIDATE_WINDOW_START:
                observed_transition_labels.add(label)
            elif month < CANDIDATE_WINDOW_END_EXCLUSIVE:
                observed_candidate_labels.add(label)
                candidate_counts[label] = candidate_counts.get(label, 0) + month_count

        monthly_total = sum(monthly_counts.values())
        if monthly_total != count:
            raise TaxonomyProfileError(
                "product_trend_reconciliation_failed",
                product_bucket_index=index,
                bucket_count=count,
                monthly_count=monthly_total,
            )

        product_total += count
        product_summaries.append(
            {
                "label": label,
                "request_window_count": count,
                "candidate_window_count": candidate_counts.get(label, 0),
                "first_observed_month": min(monthly_counts) if monthly_counts else None,
                "last_observed_month": max(monthly_counts) if monthly_counts else None,
                "monthly_counts": dict(sorted(monthly_counts.items())),
            }
        )

    observed_months: dict[str, int] = {}
    for index, raw_bucket in enumerate(date_buckets):
        bucket = _require_mapping(raw_bucket, f"date_bucket[{index}]")
        month = _month_value(bucket, f"date_bucket[{index}]")
        observed_months[month] = _require_int(
            bucket.get("doc_count"), f"date_bucket[{index}].doc_count"
        )

    expected_candidate_months = _month_sequence(
        CANDIDATE_WINDOW_START,
        CANDIDATE_WINDOW_END_EXCLUSIVE,
    )
    candidate_months_missing = sorted(set(expected_candidate_months) - set(filtered_monthly_counts))
    legacy_in_candidate = sorted(observed_candidate_labels & LEGACY_CHANGED_PRODUCT_LABELS)
    unknown_in_candidate = sorted(
        observed_candidate_labels - CURRENT_PRODUCT_LABELS - LEGACY_CHANGED_PRODUCT_LABELS
    )
    current_labels_missing = sorted(CURRENT_PRODUCT_LABELS - observed_candidate_labels)
    aggregation_count = _require_int(
        product_aggregation.get("doc_count"), "aggregations.product.doc_count"
    )
    date_range_count = _require_int(
        date_range.get("doc_count"), "aggregations.dateRangeBuckets.doc_count"
    )

    return {
        "status": "ok",
        "profile_version": "cfpb-taxonomy-stability-v1",
        "request": {
            "endpoint": "cfpb_complaint_trends_v1",
            "requested_at_utc": requested_at_utc,
            "date_received_min": EXPECTED_QUERY["date_received_min"][0],
            "date_received_max_exclusive": EXPECTED_QUERY["date_received_max"][0],
            "has_narrative": True,
            "interval": "month",
            "complaint_rows_requested": 0,
        },
        "http": {
            "status": 200,
            "content_type": content_type,
            "elapsed_ms": round(elapsed_ms, 3),
            "response_bytes": response_bytes,
        },
        "official_taxonomy": {
            "effective_date": TAXONOMY_EFFECTIVE_DATE,
            "expected_current_product_labels": sorted(CURRENT_PRODUCT_LABELS),
            "known_changed_legacy_product_labels": sorted(LEGACY_CHANGED_PRODUCT_LABELS),
        },
        "candidate_window": {
            "date_received_min": CANDIDATE_WINDOW_START,
            "date_received_max_exclusive": CANDIDATE_WINDOW_END_EXCLUSIVE,
            "expected_month_count": len(expected_candidate_months),
            "missing_months": candidate_months_missing,
            "counts_by_product": dict(sorted(candidate_counts.items())),
            "current_labels_without_observed_rows": current_labels_missing,
            "legacy_labels_observed": legacy_in_candidate,
            "unexpected_labels_observed": unknown_in_candidate,
        },
        "observed": {
            "request_window_record_count": aggregation_count,
            "product_bucket_record_count": product_total,
            "date_histogram_record_count": date_range_count,
            "transition_labels": sorted(observed_transition_labels),
            "candidate_labels": sorted(observed_candidate_labels),
            "filtered_monthly_record_counts": dict(sorted(filtered_monthly_counts.items())),
            "product_summaries": sorted(product_summaries, key=lambda value: str(value["label"])),
        },
        "non_decisional_api_context": {
            "date_range_bucket_record_count": date_range_count,
            "date_range_monthly_record_counts": dict(sorted(observed_months.items())),
            "reason": "The overview lens returns this UI context series outside the filters.",
        },
        "checks": {
            "aggregate_only_request": True,
            "complete_product_aggregation": True,
            "candidate_months_complete": not candidate_months_missing,
            "no_legacy_labels_in_candidate_window": not legacy_in_candidate,
            "no_unexpected_labels_in_candidate_window": not unknown_in_candidate,
            "product_counts_reconcile": product_total == aggregation_count,
            "product_monthly_counts_reconcile": True,
        },
        "privacy": {
            "complaint_rows_received": False,
            "narratives_received": False,
            "response_body_logged": False,
            "response_persisted": False,
        },
    }


def fetch_taxonomy_profile(
    *,
    url: str = CFPB_TAXONOMY_PROFILE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    opener: OpenerLike | None = None,
    requested_at_utc: str | None = None,
    clock: Callable[[], float] = perf_counter,
) -> dict[str, object]:
    """Make one fixed aggregate request and return a safe taxonomy profile."""

    validate_taxonomy_profile_url(url)
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
            content_type = _content_type(response.headers)
            if response.status != 200:
                raise TaxonomyProfileError(
                    "http_error",
                    requested_at_utc=request_timestamp,
                    http_status=response.status,
                    content_type=content_type,
                )
            if content_type != "application/json" and not content_type.endswith("+json"):
                raise TaxonomyProfileError(
                    "unexpected_content_type",
                    requested_at_utc=request_timestamp,
                    http_status=response.status,
                    content_type=content_type,
                )
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise TaxonomyProfileError(
                    "response_byte_limit_exceeded",
                    requested_at_utc=request_timestamp,
                    approved_byte_limit=MAX_RESPONSE_BYTES,
                )
        elapsed_ms = (clock() - started) * 1000
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TaxonomyProfileError(
                "invalid_json_response",
                requested_at_utc=request_timestamp,
            ) from error
        return build_safe_taxonomy_profile(
            payload,
            requested_at_utc=request_timestamp,
            elapsed_ms=elapsed_ms,
            response_bytes=len(raw),
            content_type=content_type,
        )
    except TaxonomyProfileError:
        raise
    except HTTPError as error:
        raise TaxonomyProfileError(
            "http_error",
            requested_at_utc=request_timestamp,
            http_status=error.code,
            content_type=_content_type(error.headers),
        ) from None
    except (TimeoutError, URLError):
        raise TaxonomyProfileError("network_error", requested_at_utc=request_timestamp) from None


def safe_taxonomy_error_report(error: TaxonomyProfileError) -> dict[str, object]:
    complaint_rows_received = error.code == "unexpected_complaint_rows"
    return {
        "status": "error",
        "error": {"code": error.code, **error.safe_details},
        "privacy": {
            "complaint_rows_received": complaint_rows_received,
            "narratives_received": None if complaint_rows_received else False,
            "narrative_fields_inspected": False,
            "response_body_logged": False,
            "response_persisted": False,
        },
    }


def _assert_no_complaint_hits(root: Mapping[str, Any]) -> None:
    """Reject a response if the upstream service returns any row-level hits."""

    if "hits" not in root:
        return
    hits_container = _require_mapping(root["hits"], "hits")
    hits = _require_list(hits_container.get("hits"), "hits.hits")
    if hits:
        raise TaxonomyProfileError(
            "unexpected_complaint_rows",
            returned_row_count=len(hits),
        )


def _require_mapping(value: object, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TaxonomyProfileError("invalid_response_shape", location=location)
    return value


def _require_list(value: object, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise TaxonomyProfileError("invalid_response_shape", location=location)
    return value


def _require_int(value: object, location: str) -> int:
    if type(value) is not int or value < 0:
        raise TaxonomyProfileError("invalid_response_shape", location=location)
    return value


def _month_value(bucket: Mapping[str, Any], location: str) -> str:
    raw_value = bucket.get("key_as_string")
    if not isinstance(raw_value, str):
        raise TaxonomyProfileError("invalid_response_shape", location=location)
    month = raw_value[:10]
    try:
        parsed = date.fromisoformat(month)
    except ValueError as error:
        raise TaxonomyProfileError("invalid_response_shape", location=location) from error
    if parsed.day != 1:
        raise TaxonomyProfileError("invalid_response_shape", location=location)
    return parsed.isoformat()


def _month_sequence(start: str, end_exclusive: str) -> tuple[str, ...]:
    current = date.fromisoformat(start)
    end = date.fromisoformat(end_exclusive)
    months: list[str] = []
    while current < end:
        months.append(current.isoformat())
        next_year = current.year + int(current.month == 12)
        current = date(next_year, current.month % 12 + 1, 1)
    return tuple(months)


def _content_type(headers: Any) -> str:
    get_content_type = getattr(headers, "get_content_type", None)
    if callable(get_content_type):
        return str(get_content_type()).lower()
    value = headers.get("Content-Type", "") if hasattr(headers, "get") else ""
    return str(value).split(";", maxsplit=1)[0].strip().lower()
