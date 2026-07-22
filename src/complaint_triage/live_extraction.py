"""Narrow live transport and orchestration for the approved CFPB extraction."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener

from complaint_triage.real_extraction import (
    PROJECT_ROOT,
    REAL_RETENTION_DEADLINE_UTC,
    REAL_RETENTION_POLICY_ID,
    ExtractionContext,
    ExtractionError,
    PublishedShard,
    StreamResponse,
    approved_monthly_shards,
    export_parameters,
    publish_export_shard,
    publish_run_manifest,
    validate_preflight_counts,
)
from complaint_triage.taxonomy_profile import (
    NoRedirectHandler,
    TaxonomyProfileError,
    fetch_taxonomy_profile,
)

CFPB_HOST = "www.consumerfinance.gov"
CFPB_EXPORT_PATH = "/data-research/consumer-complaints/search/api/v1/"
CFPB_EXPORT_BASE_URL = f"https://{CFPB_HOST}{CFPB_EXPORT_PATH}"
USER_AGENT = "complaint-triage-monthly-export/1.0"
DEFAULT_TIMEOUT_SECONDS = 180.0
CHUNK_SIZE = 64 * 1024
MIN_FREE_BYTES = 20 * 1024 * 1024 * 1024
MIN_EXPORT_START_INTERVAL_SECONDS = 35.0


class ResponseLike(Protocol):
    status: int
    headers: Any

    def read(self, amount: int | None = None) -> bytes: ...

    def geturl(self) -> str: ...

    def __enter__(self) -> ResponseLike: ...

    def __exit__(self, *args: object) -> None: ...


class OpenerLike(Protocol):
    def open(self, request: Request, timeout: float) -> ResponseLike: ...


def read_git_lineage(repository_root: Path) -> tuple[str, bool]:
    """Return HEAD and cleanliness without interpreting shell text."""

    root = repository_root.resolve()
    head = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    status = subprocess.run(
        ("git", "status", "--porcelain=v1"),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    commit = head.stdout.strip()
    clean = head.returncode == 0 and status.returncode == 0 and not status.stdout.strip()
    return commit, clean


def build_export_url(spec, expected_count: int) -> str:
    parameters = export_parameters(spec, expected_count)
    return f"{CFPB_EXPORT_BASE_URL}?{urlencode(parameters)}"


def validate_export_url(url: str, spec, expected_count: int) -> None:
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != CFPB_HOST
        or parts.path != CFPB_EXPORT_PATH
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
    ):
        raise ExtractionError("unsafe_export_request_boundary", month=spec.month)
    try:
        port = parts.port
    except ValueError as error:
        raise ExtractionError("unsafe_export_request_boundary", month=spec.month) from error
    if port not in (None, 443):
        raise ExtractionError("unsafe_export_request_boundary", month=spec.month)
    expected = {key: [value] for key, value in export_parameters(spec, expected_count).items()}
    if parse_qs(parts.query, keep_blank_values=True) != expected:
        raise ExtractionError("unsafe_export_request_parameters", month=spec.month)


def acquire_real_run(
    *,
    confirmation: str,
    repository_root: Path = PROJECT_ROOT,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    opener: OpenerLike | None = None,
    profile_fetcher: Callable[[], Mapping[str, Any]] = fetch_taxonomy_profile,
    lineage_reader: Callable[[Path], tuple[str, bool]] = read_git_lineage,
    free_space_reader: Callable[[Path], int] = lambda path: shutil.disk_usage(path).free,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Preflight and stream the exact approved run, returning aggregate evidence."""

    if confirmation != REAL_RETENTION_POLICY_ID:
        raise ExtractionError("live_acquisition_confirmation_invalid")
    root = repository_root.resolve()
    commit_sha, working_tree_clean = lineage_reader(root)
    if len(commit_sha) != 40 or any(
        character not in "0123456789abcdef" for character in commit_sha
    ):
        raise ExtractionError("git_lineage_invalid")
    if not working_tree_clean:
        raise ExtractionError("real_acquisition_requires_clean_commit")
    if timeout_seconds <= 0 or timeout_seconds > DEFAULT_TIMEOUT_SECONDS:
        raise ExtractionError("export_timeout_invalid")
    free_bytes = free_space_reader(root)
    if free_bytes < MIN_FREE_BYTES:
        raise ExtractionError(
            "insufficient_local_disk_space",
            required_free_bytes=MIN_FREE_BYTES,
            observed_free_bytes=free_bytes,
        )

    try:
        profile = profile_fetcher()
    except TaxonomyProfileError as error:
        raise ExtractionError("aggregate_preflight_failed", profile_error_code=error.code) from None
    counts = _preflight_counts(profile)
    started_at = now().astimezone(UTC)
    if started_at >= REAL_RETENTION_DEADLINE_UTC:
        raise ExtractionError("real_retention_expired")
    run_seed = f"{started_at.isoformat()}:{commit_sha}".encode()
    run_suffix = hashlib.sha256(run_seed).hexdigest()[:12]
    timestamp = started_at.replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"cfpb-run-{timestamp}-{run_suffix}"
    transport = opener or build_opener(NoRedirectHandler())
    pace_live_transport = opener is None

    published: list[PublishedShard] = []
    previous_request_started: float | None = None
    try:
        for spec in approved_monthly_shards():
            expected_count = counts[spec.month]
            url = build_export_url(spec, expected_count)
            validate_export_url(url, spec, expected_count)
            request = Request(
                url,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                method="GET",
            )
            if pace_live_transport and previous_request_started is not None:
                delay = _required_pacing_delay(previous_request_started, monotonic())
                if delay > 0:
                    sleeper(delay)
            previous_request_started = monotonic()
            with transport.open(request, timeout=timeout_seconds) as response:
                content_type = _header(response.headers, "Content-Type")
                content_encoding = _header(response.headers, "Content-Encoding").lower()
                if content_encoding not in {"", "identity"}:
                    raise ExtractionError("export_content_encoding_invalid", month=spec.month)
                redirected = response.geturl() != url
                context = ExtractionContext(
                    run_id=run_id,
                    retrieved_at_utc=now().astimezone(UTC),
                    expires_at_utc=REAL_RETENTION_DEADLINE_UTC,
                    code_commit_sha=commit_sha,
                    working_tree_clean=True,
                )
                published.append(
                    publish_export_shard(
                        spec,
                        expected_count=expected_count,
                        response=StreamResponse(
                            status_code=response.status,
                            content_type=content_type,
                            redirected=redirected,
                            chunks=iter(lambda: response.read(CHUNK_SIZE), b""),
                        ),
                        context=context,
                        repository_root=root,
                    )
                )
    except ExtractionError:
        _rollback_incomplete_run(published, root, run_id)
        raise
    except HTTPError as error:
        _rollback_incomplete_run(published, root, run_id)
        raise ExtractionError("export_http_error", status=error.code) from None
    except (TimeoutError, URLError, OSError):
        _rollback_incomplete_run(published, root, run_id)
        raise ExtractionError("export_network_error") from None

    run_context = ExtractionContext(
        run_id=run_id,
        retrieved_at_utc=started_at,
        expires_at_utc=REAL_RETENTION_DEADLINE_UTC,
        code_commit_sha=commit_sha,
        working_tree_clean=True,
    )
    run_path = publish_run_manifest(published, context=run_context, repository_root=root)
    return {
        "status": "acquired",
        "run_id": run_id,
        "run_manifest_relative_path": run_path.relative_to(root).as_posix(),
        "code_commit_sha": commit_sha,
        "preflight_record_count": sum(counts.values()),
        "published_record_count": sum(shard.returned_record_count for shard in published),
        "published_shard_count": len(published),
        "artifact_byte_count": sum(shard.artifact_byte_count for shard in published),
        "retention": {
            "policy_id": REAL_RETENTION_POLICY_ID,
            "expires_at_utc": REAL_RETENTION_DEADLINE_UTC.isoformat().replace("+00:00", "Z"),
        },
        "privacy": {"source_values_logged": False, "response_body_logged": False},
    }


def _preflight_counts(profile: Mapping[str, Any]) -> dict[str, int]:
    try:
        if profile["status"] != "ok" or profile["request"]["complaint_rows_requested"] != 0:
            raise ExtractionError("aggregate_preflight_invalid")
        candidate = profile["candidate_window"]
        if (
            candidate["missing_months"]
            or candidate["legacy_labels_observed"]
            or candidate["unexpected_labels_observed"]
        ):
            raise ExtractionError("aggregate_preflight_invalid")
        raw_counts = profile["observed"]["filtered_monthly_record_counts"]
        counts = {
            spec.month: raw_counts[spec.start_inclusive] for spec in approved_monthly_shards()
        }
    except (KeyError, TypeError) as error:
        raise ExtractionError("aggregate_preflight_invalid") from error
    return validate_preflight_counts(counts)


def safe_live_result(error: ExtractionError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {"source_values_logged": False, "response_body_logged": False},
    }


def _rollback_incomplete_run(
    published: list[PublishedShard], repository_root: Path, run_id: str
) -> None:
    root = repository_root.resolve()
    for shard in reversed(published):
        if shard.manifest_created:
            manifest = (root / Path(*shard.manifest_relative_path.split("/"))).resolve()
            expected_manifest_root = (root / "data" / "manifests" / "cfpb").resolve()
            if manifest.parent != expected_manifest_root:
                raise ExtractionError("incomplete_run_rollback_unsafe")
            manifest.unlink(missing_ok=True)
        if shard.artifact_created:
            artifact = (root / Path(*shard.artifact_relative_path.split("/"))).resolve()
            expected_artifact_root = (root / "data" / "raw" / "cfpb" / "sha256").resolve()
            if not artifact.is_relative_to(expected_artifact_root):
                raise ExtractionError("incomplete_run_rollback_unsafe")
            artifact.unlink(missing_ok=True)
    temporary = (root / "data" / "raw" / "cfpb" / ".tmp" / run_id).resolve()
    if temporary.exists() and not any(temporary.iterdir()):
        temporary.rmdir()


def _header(headers: Any, name: str) -> str:
    return str(headers.get(name, "")) if hasattr(headers, "get") else ""


def _required_pacing_delay(previous_started: float, current: float) -> float:
    return max(0.0, MIN_EXPORT_START_INTERVAL_SECONDS - (current - previous_started))
