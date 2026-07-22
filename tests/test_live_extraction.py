import json
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from complaint_triage.live_extraction import (
    CFPB_EXPORT_PATH,
    MIN_FREE_BYTES,
    acquire_real_run,
    build_export_url,
    safe_live_result,
    validate_export_url,
)
from complaint_triage.real_extraction import (
    REAL_RETENTION_POLICY_ID,
    ExtractionError,
    approved_monthly_shards,
)

NOW = datetime(2026, 7, 22, 13, 0, tzinfo=UTC)


class FakeResponse:
    def __init__(
        self,
        url: str,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "text/json",
        content_encoding: str = "",
        final_url: str | None = None,
    ) -> None:
        self.status = status
        self.url = url
        self.final_url = final_url or url
        self.body = body
        self.offset = 0
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if content_encoding:
            self.headers["Content-Encoding"] = content_encoding

    def read(self, amount=None):
        if amount is None:
            amount = len(self.body)
        value = self.body[self.offset : self.offset + amount]
        self.offset += len(value)
        return value

    def geturl(self):
        return self.final_url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class FakeOpener:
    def __init__(self, *, response_changes=None, fail_at: int | None = None) -> None:
        self.requests = []
        self.response_changes = response_changes or {}
        self.fail_at = fail_at

    def open(self, request, timeout):
        url = request.full_url
        self.requests.append((url, timeout, dict(request.header_items())))
        query = parse_qs(urlsplit(url).query)
        month = query["date_received_min"][0][:7]
        body = json.dumps(
            [
                {
                    "_index": "complaints-v1",
                    "_source": {
                        "complaint_id": f"SYN-{month}-1",
                        "complaint_what_happened": "SYNTHETIC TEST RECORD. One.",
                        "date_received": query["date_received_min"][0],
                        "has_narrative": True,
                        "product": "SYNTHETIC PRODUCT",
                    },
                },
                {
                    "_index": "complaints-v1",
                    "_source": {
                        "complaint_id": f"SYN-{month}-2",
                        "complaint_what_happened": "SYNTHETIC TEST RECORD. Two.",
                        "date_received": query["date_received_min"][0],
                        "has_narrative": True,
                        "product": "SYNTHETIC PRODUCT",
                    },
                },
            ]
        ).encode()
        changes = self.response_changes
        if self.fail_at == len(self.requests):
            changes = {"status": 503}
        return FakeResponse(url, body, **changes)


def profile() -> dict:
    return {
        "status": "ok",
        "request": {"complaint_rows_requested": 0},
        "candidate_window": {
            "missing_months": [],
            "legacy_labels_observed": [],
            "unexpected_labels_observed": [],
        },
        "observed": {
            "filtered_monthly_record_counts": {
                spec.start_inclusive: 2 for spec in approved_monthly_shards()
            }
        },
    }


def clean_lineage(_root: Path) -> tuple[str, bool]:
    return "a" * 40, True


def test_export_url_is_exactly_bounded_to_approved_query() -> None:
    spec = approved_monthly_shards()[0]
    url = build_export_url(spec, 42_517)
    validate_export_url(url, spec, 42_517)
    parts = urlsplit(url)

    assert parts.path == CFPB_EXPORT_PATH
    assert parse_qs(parts.query)["date_received_max"] == ["2023-09-30"]
    with pytest.raises(ExtractionError, match="unsafe_export_request_boundary"):
        validate_export_url(url.replace("www.consumerfinance.gov", "example.com"), spec, 42_517)
    with pytest.raises(ExtractionError, match="unsafe_export_request_parameters"):
        validate_export_url(f"{url}&search_term=unsafe", spec, 42_517)


def test_live_run_publishes_exactly_sixteen_synthetic_shards(tmp_path: Path) -> None:
    opener = FakeOpener()
    report = acquire_real_run(
        confirmation=REAL_RETENTION_POLICY_ID,
        repository_root=tmp_path,
        opener=opener,
        profile_fetcher=profile,
        lineage_reader=clean_lineage,
        now=lambda: NOW,
    )

    assert report["published_shard_count"] == 16
    assert report["preflight_record_count"] == report["published_record_count"] == 32
    assert len(opener.requests) == 16
    assert all(request[2]["Accept"] == "application/json" for request in opener.requests)
    run_manifest = tmp_path / Path(*report["run_manifest_relative_path"].split("/"))
    assert len(json.loads(run_manifest.read_text())["shards"]) == 16


def test_dirty_tree_fails_before_preflight_or_network(tmp_path: Path) -> None:
    opener = FakeOpener()
    profile_called = False

    def should_not_profile():
        nonlocal profile_called
        profile_called = True
        return profile()

    with pytest.raises(ExtractionError, match="real_acquisition_requires_clean_commit"):
        acquire_real_run(
            confirmation=REAL_RETENTION_POLICY_ID,
            repository_root=tmp_path,
            opener=opener,
            profile_fetcher=should_not_profile,
            lineage_reader=lambda _root: ("a" * 40, False),
            now=lambda: NOW,
        )

    assert profile_called is False
    assert opener.requests == []


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"content_encoding": "gzip"}, "export_content_encoding_invalid"),
        ({"content_type": "text/html"}, "export_content_type_invalid"),
        ({"status": 503}, "export_http_status_invalid"),
        ({"final_url": "https://example.com/redirect"}, "export_redirect_rejected"),
    ],
)
def test_live_response_boundary_fails_closed(tmp_path: Path, changes: dict, code: str) -> None:
    with pytest.raises(ExtractionError, match=code):
        acquire_real_run(
            confirmation=REAL_RETENTION_POLICY_ID,
            repository_root=tmp_path,
            opener=FakeOpener(response_changes=changes),
            profile_fetcher=profile,
            lineage_reader=clean_lineage,
            now=lambda: NOW,
        )


def test_confirmation_and_aggregate_preflight_fail_before_network(tmp_path: Path) -> None:
    opener = FakeOpener()
    with pytest.raises(ExtractionError, match="live_acquisition_confirmation_invalid"):
        acquire_real_run(
            confirmation="wrong",
            repository_root=tmp_path,
            opener=opener,
            profile_fetcher=profile,
            lineage_reader=clean_lineage,
            now=lambda: NOW,
        )
    changed = profile()
    changed["observed"]["filtered_monthly_record_counts"].pop("2024-12-01")
    with pytest.raises(ExtractionError, match="aggregate_preflight_invalid"):
        acquire_real_run(
            confirmation=REAL_RETENTION_POLICY_ID,
            repository_root=tmp_path,
            opener=opener,
            profile_fetcher=lambda: changed,
            lineage_reader=clean_lineage,
            now=lambda: NOW,
        )
    assert opener.requests == []


def test_disk_capacity_fails_before_preflight_or_network(tmp_path: Path) -> None:
    opener = FakeOpener()
    with pytest.raises(ExtractionError, match="insufficient_local_disk_space"):
        acquire_real_run(
            confirmation=REAL_RETENTION_POLICY_ID,
            repository_root=tmp_path,
            opener=opener,
            profile_fetcher=profile,
            lineage_reader=clean_lineage,
            free_space_reader=lambda _root: MIN_FREE_BYTES - 1,
            now=lambda: NOW,
        )
    assert opener.requests == []


def test_live_error_report_contains_no_response_body() -> None:
    report = safe_live_result(ExtractionError("export_network_error", month="2023-09"))
    assert report["privacy"] == {"source_values_logged": False, "response_body_logged": False}


def test_incomplete_run_rolls_back_only_newly_published_files(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError, match="export_http_status_invalid"):
        acquire_real_run(
            confirmation=REAL_RETENTION_POLICY_ID,
            repository_root=tmp_path,
            opener=FakeOpener(fail_at=3),
            profile_fetcher=profile,
            lineage_reader=clean_lineage,
            now=lambda: NOW,
        )

    assert not list((tmp_path / "data" / "raw" / "cfpb").rglob("*.json"))
    assert not list((tmp_path / "data" / "manifests" / "cfpb").glob("*.json"))
