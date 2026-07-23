"""Training-only token-length profile for the proposed compact transformer."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Protocol

import psycopg
from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.analytical_population import POPULATION_VERSION
from complaint_triage.db import DatabaseSettings
from complaint_triage.live_extraction import read_git_lineage
from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.taxonomy import CURRENT_PRODUCT_LABELS
from complaint_triage.temporal_split import SPLIT_SCHEMA_PATH, SPLIT_VERSION

REPORT_VERSION = "tokenizer-profile-1.0.0"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-transformer-token-profile.schema.json"
MODEL_ID = "microsoft/MiniLM-L12-H384-uncased"
MODEL_REVISION = "9a201d7b3ebebc5feabf9fbb4b3a4ec5d3f2440d"
MODEL_MAX_POSITIONS = 512
CANDIDATE_LENGTHS = (128, 256, 384, 512)
QUANTILES = (("p50", 0.50), ("p75", 0.75), ("p90", 0.90), ("p95", 0.95), ("p99", 0.99))
FETCH_SIZE = 2_000
TOKENIZE_BATCH_SIZE = 256
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")

LineageReader = Callable[[Path], tuple[str, bool]]
Clock = Callable[[], datetime]
SoftwareReader = Callable[[], Mapping[str, str]]


class Tokenizer(Protocol):
    is_fast: bool
    vocab_size: int

    def __call__(self, texts: Sequence[str], **kwargs: Any) -> Mapping[str, Any]: ...

    def num_special_tokens_to_add(self, *, pair: bool) -> int: ...


@dataclass(frozen=True)
class TokenizerBundle:
    tokenizer: Tokenizer
    tokenizer_class: str
    config_class: str
    max_position_embeddings: int
    hidden_size: int
    hidden_layers: int


@dataclass
class LengthHistogram:
    counts: Counter[int] = field(default_factory=Counter)
    record_count: int = 0
    token_count: int = 0
    minimum: int | None = None
    maximum: int | None = None

    def add(self, length: int) -> None:
        if isinstance(length, bool) or not isinstance(length, int) or length <= 0:
            raise TransformerTokenProfileError("token_profile_length_invalid")
        self.counts[length] += 1
        self.record_count += 1
        self.token_count += length
        self.minimum = length if self.minimum is None else min(self.minimum, length)
        self.maximum = length if self.maximum is None else max(self.maximum, length)

    def as_report(self) -> dict[str, Any]:
        if not self.record_count or self.minimum is None or self.maximum is None:
            raise TransformerTokenProfileError("token_profile_distribution_empty")
        return {
            "record_count": self.record_count,
            "token_count": self.token_count,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "mean": round(self.token_count / self.record_count, 6),
            "quantiles": {name: self._nearest_rank(probability) for name, probability in QUANTILES},
            "candidate_lengths": [self._candidate_report(value) for value in CANDIDATE_LENGTHS],
        }

    def _nearest_rank(self, probability: float) -> int:
        target = math.ceil(probability * self.record_count)
        cumulative = 0
        for length in sorted(self.counts):
            cumulative += self.counts[length]
            if cumulative >= target:
                return length
        raise TransformerTokenProfileError("token_profile_quantile_failed")

    def _candidate_report(self, maximum_length: int) -> dict[str, Any]:
        exceeding = sum(count for length, count in self.counts.items() if length > maximum_length)
        retained = sum(min(length, maximum_length) * count for length, count in self.counts.items())
        return {
            "maximum_length": maximum_length,
            "records_exceeding": exceeding,
            "share_records_exceeding": round(exceeding / self.record_count, 6),
            "retained_token_ratio": round(retained / self.token_count, 6),
        }


class TransformerTokenProfileError(Exception):
    """A controlled profiling failure containing no source row values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_transformer_token_profile_error(
    error: TransformerTokenProfileError,
) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "complaint_ids_logged": False,
            "token_ids_logged": False,
            "vocabulary_logged": False,
            "row_values_in_report": False,
        },
    }


def profile_transformer_tokens(
    split_manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
    lineage_reader: LineageReader = read_git_lineage,
    clock: Clock = lambda: datetime.now(UTC),
    row_loader: Callable[[Mapping[str, Any], DatabaseSettings], Iterable[tuple[str, str]]]
    | None = None,
    tokenizer_loader: Callable[[Path], TokenizerBundle] | None = None,
    software_reader: SoftwareReader | None = None,
) -> dict[str, Any]:
    """Publish an aggregate token-length report using training narratives only."""

    root = repository_root.resolve()
    manifest, manifest_bytes = _load_split_manifest(split_manifest_path, root)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    report_path = _report_path(root, manifest["run_id"])
    if report_path.exists():
        report = _load_existing_report(report_path)
        if report["source"]["split_manifest_sha256"] != manifest_sha256:
            raise TransformerTokenProfileError("token_profile_report_identity_conflict")
        return report

    commit_sha, clean = lineage_reader(root)
    if not SHA40_PATTERN.fullmatch(commit_sha) or not clean:
        raise TransformerTokenProfileError("token_profile_requires_clean_commit")
    created_at = clock()
    if created_at.tzinfo is None or created_at.utcoffset() != UTC.utcoffset(created_at):
        raise TransformerTokenProfileError("token_profile_clock_invalid")

    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")
    load_rows = row_loader or iter_training_rows
    load_tokenizer = tokenizer_loader or load_pinned_tokenizer
    bundle = load_tokenizer(root)
    _validate_tokenizer_bundle(bundle)
    started = time.perf_counter()
    overall, by_class = profile_training_rows(
        load_rows(manifest, database_settings),
        bundle.tokenizer,
        expected_counts=manifest["class_counts_by_split"]["train"],
    )
    elapsed = time.perf_counter() - started
    labels = tuple(sorted(CURRENT_PRODUCT_LABELS))
    report = {
        "report_version": REPORT_VERSION,
        "run_id": manifest["run_id"],
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "source": {
            "split_manifest_sha256": manifest_sha256,
            "split_version": SPLIT_VERSION,
            "profiling_implementation_commit_sha": commit_sha,
        },
        "data": {
            "feature_input": "consumer_complaint_narrative_only",
            "profiled_split": "train",
            "queried_splits": ["train"],
            "train_record_count": overall.record_count,
            "validation_accessed": False,
            "test_accessed": False,
            "labels": list(labels),
        },
        "tokenizer": {
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "tokenizer_class": bundle.tokenizer_class,
            "config_class": bundle.config_class,
            "fast": True,
            "vocabulary_size": bundle.tokenizer.vocab_size,
            "special_tokens_per_single_sequence": bundle.tokenizer.num_special_tokens_to_add(
                pair=False
            ),
            "model_max_position_embeddings": bundle.max_position_embeddings,
            "hidden_size": bundle.hidden_size,
            "hidden_layers": bundle.hidden_layers,
            "add_special_tokens": True,
            "truncation_during_measurement": False,
            "padding_during_measurement": False,
            "batch_size": TOKENIZE_BATCH_SIZE,
        },
        "measurement": {
            "quantile_method": "nearest_rank",
            "candidate_maximum_lengths": list(CANDIDATE_LENGTHS),
            "elapsed_seconds": round(elapsed, 3),
            "overall": overall.as_report(),
            "by_class": {label: by_class[label].as_report() for label in labels},
        },
        "software": dict((software_reader or _software_versions)()),
        "checks": {
            "source_counts_reconcile": True,
            "taxonomy_complete": True,
            "tokenizer_revision_pinned": True,
            "train_only_query": True,
            "validation_accessed": False,
            "test_accessed": False,
            "no_model_weights_loaded": True,
            "no_classifier_trained": True,
        },
        "decision": {
            "maximum_length_selected": False,
            "requires_owner_approval": True,
            "next_gate": "select_maximum_length_before_CT-302",
        },
        "claims": {
            "portfolio_promotion_approved": False,
            "predictive_performance_measured": False,
            "interpretation": "training_input_retention_profile_not_model_performance",
        },
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_token_ids": False,
            "contains_vocabulary": False,
            "cache_contains_governed_vocabulary": True,
            "cache_git_tracking_allowed": False,
            "report_git_tracking_allowed": True,
        },
    }
    _validate_report(report)
    _atomic_json(report_path, report)
    return report


def load_pinned_tokenizer(root: Path) -> TokenizerBundle:
    """Load only tokenizer/config files from one immutable model revision."""

    try:
        from transformers import AutoConfig, AutoTokenizer
    except ImportError as error:
        raise TransformerTokenProfileError("token_profile_dependency_missing") from error

    cache_dir = root / "data" / "model_cache" / "huggingface"
    try:
        config = AutoConfig.from_pretrained(
            MODEL_ID,
            revision=MODEL_REVISION,
            cache_dir=cache_dir,
            trust_remote_code=False,
        )
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ID,
            revision=MODEL_REVISION,
            cache_dir=cache_dir,
            use_fast=True,
            trust_remote_code=False,
        )
    except (OSError, ValueError) as error:
        raise TransformerTokenProfileError("token_profile_tokenizer_load_failed") from error
    if getattr(config, "_commit_hash", None) != MODEL_REVISION:
        raise TransformerTokenProfileError("token_profile_revision_mismatch")
    return TokenizerBundle(
        tokenizer=tokenizer,
        tokenizer_class=type(tokenizer).__name__,
        config_class=type(config).__name__,
        max_position_embeddings=int(config.max_position_embeddings),
        hidden_size=int(config.hidden_size),
        hidden_layers=int(config.num_hidden_layers),
    )


def iter_training_rows(
    manifest: Mapping[str, Any], settings: DatabaseSettings
) -> Iterable[tuple[str, str]]:
    """Stream only included training narratives and target labels."""

    query = """
        SELECT s.narrative, p.target_product
        FROM analytical.split_outcomes o
        JOIN analytical.population_outcomes p
          ON p.raw_batch_id = o.raw_batch_id
         AND p.source_row_ordinal = o.source_row_ordinal
         AND p.staging_transformation_version = o.staging_transformation_version
         AND p.population_version = o.population_version
        JOIN staging.complaint_outcomes s
          ON s.raw_batch_id = o.raw_batch_id
         AND s.source_row_ordinal = o.source_row_ordinal
         AND s.transformation_version = o.staging_transformation_version
        WHERE o.run_id = %s AND o.split_version = %s
          AND o.population_version = %s
          AND o.disposition = 'included'
          AND o.split_assignment = 'train'
        ORDER BY o.raw_batch_id, o.source_row_ordinal
    """
    parameters = (manifest["run_id"], SPLIT_VERSION, POPULATION_VERSION)
    try:
        with psycopg.connect(settings.psycopg_conninfo()) as connection:
            with connection.cursor(name=f"token_profile_rows_{uuid.uuid4().hex}") as cursor:
                cursor.execute(query, parameters)
                while rows := cursor.fetchmany(FETCH_SIZE):
                    yield from rows
    except psycopg.Error as error:
        raise TransformerTokenProfileError("token_profile_database_failed") from error


def profile_training_rows(
    rows: Iterable[tuple[str, str]],
    tokenizer: Tokenizer,
    *,
    expected_counts: Mapping[str, int],
) -> tuple[LengthHistogram, dict[str, LengthHistogram]]:
    """Tokenize bounded batches and retain aggregate length histograms only."""

    labels = tuple(sorted(CURRENT_PRODUCT_LABELS))
    if set(expected_counts) != set(labels):
        raise TransformerTokenProfileError("token_profile_expected_taxonomy_invalid")
    overall = LengthHistogram()
    by_class = {label: LengthHistogram() for label in labels}
    text_batch: list[str] = []
    label_batch: list[str] = []

    def consume_batch() -> None:
        if not text_batch:
            return
        try:
            encoded = tokenizer(
                text_batch,
                add_special_tokens=True,
                padding=False,
                truncation=False,
                return_attention_mask=False,
                return_token_type_ids=False,
                verbose=False,
            )
            input_ids = encoded["input_ids"]
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            raise TransformerTokenProfileError("token_profile_tokenization_failed") from error
        if len(input_ids) != len(text_batch):
            raise TransformerTokenProfileError("token_profile_tokenization_count_mismatch")
        for token_ids, label in zip(input_ids, label_batch, strict=True):
            length = len(token_ids)
            overall.add(length)
            by_class[label].add(length)
        text_batch.clear()
        label_batch.clear()

    for narrative, label in rows:
        if not isinstance(narrative, str) or not narrative.strip():
            raise TransformerTokenProfileError("token_profile_source_row_invalid")
        if label not in by_class:
            raise TransformerTokenProfileError("token_profile_source_taxonomy_invalid")
        text_batch.append(narrative)
        label_batch.append(label)
        if len(text_batch) == TOKENIZE_BATCH_SIZE:
            consume_batch()
    consume_batch()

    observed_counts = {label: by_class[label].record_count for label in labels}
    if observed_counts != dict(expected_counts):
        raise TransformerTokenProfileError("token_profile_source_counts_do_not_reconcile")
    return overall, by_class


def _validate_tokenizer_bundle(bundle: TokenizerBundle) -> None:
    if not bundle.tokenizer.is_fast:
        raise TransformerTokenProfileError("token_profile_fast_tokenizer_required")
    if bundle.max_position_embeddings != MODEL_MAX_POSITIONS:
        raise TransformerTokenProfileError("token_profile_model_boundary_mismatch")
    if (
        bundle.tokenizer.vocab_size <= 0
        or bundle.tokenizer.num_special_tokens_to_add(pair=False) <= 0
    ):
        raise TransformerTokenProfileError("token_profile_tokenizer_metadata_invalid")


def _software_versions() -> dict[str, str]:
    try:
        return {
            "python": platform.python_version(),
            "transformers": version("transformers"),
            "tokenizers": version("tokenizers"),
            "huggingface_hub": version("huggingface-hub"),
        }
    except ImportError as error:
        raise TransformerTokenProfileError("token_profile_dependency_missing") from error


def _load_split_manifest(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    resolved = path.resolve()
    if resolved.parent != (root / "data" / "manifests" / "cfpb" / "splits").resolve():
        raise TransformerTokenProfileError("unsafe_split_manifest_path")
    try:
        encoded = resolved.read_bytes()
        manifest = json.loads(encoded)
        schema = json.loads(SPLIT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerTokenProfileError("token_profile_split_manifest_unreadable") from error
    if not isinstance(manifest, dict):
        raise TransformerTokenProfileError("token_profile_split_manifest_schema_invalid")
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)
    )
    if errors:
        raise TransformerTokenProfileError(
            "token_profile_split_manifest_schema_invalid", issue_count=len(errors)
        )
    return manifest, encoded


def _report_path(root: Path, run_id: str) -> Path:
    return (
        root
        / "data"
        / "evaluations"
        / "cfpb"
        / "tokenizer-profile"
        / f"{run_id}-{REPORT_VERSION}.json"
    )


def _load_existing_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerTokenProfileError("token_profile_report_unreadable") from error
    if not isinstance(report, dict):
        raise TransformerTokenProfileError("token_profile_report_schema_invalid")
    _validate_report(report)
    return report


def _validate_report(report: Mapping[str, Any]) -> None:
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise TransformerTokenProfileError(
            "token_profile_report_schema_invalid", issue_count=len(errors)
        )


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as destination:
            destination.write(encoded)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise TransformerTokenProfileError("token_profile_report_write_failed") from error
    finally:
        temporary.unlink(missing_ok=True)
