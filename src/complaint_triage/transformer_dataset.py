"""Deterministic train/validation dataset pipeline for the compact transformer."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import re
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
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
from complaint_triage.transformer_token_profile import (
    MODEL_ID,
    MODEL_REVISION,
    TokenizerBundle,
    TransformerTokenProfileError,
    load_pinned_tokenizer,
)

REPORT_VERSION = "transformer-dataset-validation-1.0.0"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-transformer-dataset.schema.json"
MAXIMUM_LENGTH = 384
TOKENIZE_BATCH_SIZE = 256
COLLATION_CHECK_BATCH_SIZE = 32
PAD_TO_MULTIPLE_OF = 8
SHUFFLE_BUFFER_SIZE = 8_192
RANDOM_SEED = 42
FETCH_SIZE = 2_000
ALLOWED_SPLITS = ("train", "validation")
LABELS = tuple(sorted(CURRENT_PRODUCT_LABELS))
LABEL_TO_ID = {label: index for index, label in enumerate(LABELS)}
ID_TO_LABEL = {index: label for label, index in LABEL_TO_ID.items()}
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")

LineageReader = Callable[[Path], tuple[str, bool]]
Clock = Callable[[], datetime]
SoftwareReader = Callable[[], Mapping[str, str]]
RowLoader = Callable[[Mapping[str, Any], DatabaseSettings, str], Iterable[tuple[str, str]]]


class DatasetTokenizer(Protocol):
    is_fast: bool
    vocab_size: int

    def __call__(self, texts: Sequence[str], **kwargs: Any) -> Mapping[str, Any]: ...

    def pad(self, features: Sequence[Mapping[str, Any]], **kwargs: Any) -> Mapping[str, Any]: ...


class TransformerDatasetError(Exception):
    """A controlled dataset-pipeline failure containing no source row values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_transformer_dataset_error(error: TransformerDatasetError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "complaint_ids_logged": False,
            "token_ids_logged": False,
            "row_values_in_report": False,
        },
    }


def validate_transformer_dataset(
    split_manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
    lineage_reader: LineageReader = read_git_lineage,
    clock: Clock = lambda: datetime.now(UTC),
    row_loader: RowLoader | None = None,
    tokenizer_loader: Callable[[Path], TokenizerBundle] | None = None,
    software_reader: SoftwareReader | None = None,
) -> dict[str, Any]:
    """Validate canonical train/validation streams and dynamic collation."""

    root = repository_root.resolve()
    manifest, manifest_bytes = _load_split_manifest(split_manifest_path, root)
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    report_path = _report_path(root, manifest["run_id"])
    if report_path.exists():
        report = _load_existing_report(report_path)
        if report["source"]["split_manifest_sha256"] != manifest_sha256:
            raise TransformerDatasetError("transformer_dataset_report_identity_conflict")
        return report

    commit_sha, clean = lineage_reader(root)
    if not SHA40_PATTERN.fullmatch(commit_sha) or not clean:
        raise TransformerDatasetError("transformer_dataset_requires_clean_commit")
    created_at = clock()
    if created_at.tzinfo is None or created_at.utcoffset() != UTC.utcoffset(created_at):
        raise TransformerDatasetError("transformer_dataset_clock_invalid")

    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")
    load_rows = row_loader or iter_split_rows
    load_tokenizer = tokenizer_loader or _load_pinned_dataset_tokenizer
    try:
        bundle = load_tokenizer(root)
    except TransformerTokenProfileError as error:
        raise TransformerDatasetError("transformer_dataset_tokenizer_load_failed") from error
    tokenizer = bundle.tokenizer
    _validate_tokenizer(tokenizer, bundle)

    split_results: dict[str, Any] = {}
    total_started = time.perf_counter()
    for split in ALLOWED_SPLITS:
        started = time.perf_counter()
        split_results[split] = validate_split_stream(
            load_rows(manifest, database_settings, split),
            tokenizer,
            expected_counts=manifest["class_counts_by_split"][split],
        )
        split_results[split]["elapsed_seconds"] = round(time.perf_counter() - started, 3)

    report = {
        "report_version": REPORT_VERSION,
        "run_id": manifest["run_id"],
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "source": {
            "split_manifest_sha256": manifest_sha256,
            "split_version": SPLIT_VERSION,
            "dataset_implementation_commit_sha": commit_sha,
        },
        "data": {
            "feature_input": "consumer_complaint_narrative_only",
            "allowed_splits": list(ALLOWED_SPLITS),
            "queried_splits": list(ALLOWED_SPLITS),
            "test_accessed": False,
            "labels": list(LABELS),
            "label_to_id": LABEL_TO_ID,
            "id_to_label": {str(index): label for index, label in ID_TO_LABEL.items()},
        },
        "pipeline": {
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "tokenizer_class": bundle.tokenizer_class,
            "fast_tokenizer": True,
            "maximum_length": MAXIMUM_LENGTH,
            "add_special_tokens": True,
            "truncation": True,
            "stored_padding": False,
            "dynamic_padding": "longest_in_caller_batch",
            "pad_to_multiple_of": PAD_TO_MULTIPLE_OF,
            "tokenize_batch_size": TOKENIZE_BATCH_SIZE,
            "validation_collation_batch_size": COLLATION_CHECK_BATCH_SIZE,
            "training_shuffle": {
                "kind": "bounded_buffer",
                "buffer_size": SHUFFLE_BUFFER_SIZE,
                "base_seed": RANDOM_SEED,
                "epoch_seed_rule": "base_seed_plus_epoch",
                "resampling": False,
            },
            "validation_order": "canonical_source_order",
        },
        "splits": split_results,
        "timing": {"total_elapsed_seconds": round(time.perf_counter() - total_started, 3)},
        "software": dict((software_reader or _software_versions)()),
        "checks": {
            "source_counts_reconcile": True,
            "taxonomy_complete": True,
            "label_mapping_bijective": True,
            "maximum_length_enforced": True,
            "dynamic_padding_checked": True,
            "train_shuffle_deterministic": True,
            "validation_order_stable": True,
            "test_accessed": False,
            "no_rows_persisted": True,
            "no_model_weights_loaded": True,
            "no_classifier_trained": True,
        },
        "claims": {
            "portfolio_promotion_approved": False,
            "predictive_performance_measured": False,
            "interpretation": "dataset_pipeline_validation_not_model_performance",
        },
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_token_ids": False,
            "contains_vocabulary": False,
            "tokenized_dataset_persisted": False,
            "report_git_tracking_allowed": True,
        },
    }
    _validate_report(report)
    _atomic_json(report_path, report)
    return report


def stream_tokenized_split(
    manifest: Mapping[str, Any],
    settings: DatabaseSettings,
    split: str,
    tokenizer: DatasetTokenizer,
    *,
    epoch: int | None = None,
    row_loader: RowLoader | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield unpadded tokenized examples; an epoch enables train-only shuffling."""

    _validate_split(split)
    if epoch is not None and (isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0):
        raise TransformerDatasetError("transformer_dataset_epoch_invalid")
    if split == "validation" and epoch is not None:
        raise TransformerDatasetError("transformer_dataset_validation_shuffle_forbidden")
    load_rows = row_loader or iter_split_rows
    rows = load_rows(manifest, settings, split)
    if split == "train" and epoch is not None:
        rows = buffered_shuffle(
            rows,
            buffer_size=SHUFFLE_BUFFER_SIZE,
            seed=RANDOM_SEED + epoch,
        )
    yield from tokenize_rows(rows, tokenizer)


def iter_split_rows(
    manifest: Mapping[str, Any], settings: DatabaseSettings, split: str
) -> Iterable[tuple[str, str]]:
    """Stream one allowed split in stable source order."""

    _validate_split(split)
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
          AND o.split_assignment = %s
        ORDER BY o.raw_batch_id, o.source_row_ordinal
    """
    parameters = (manifest["run_id"], SPLIT_VERSION, POPULATION_VERSION, split)
    try:
        with psycopg.connect(settings.psycopg_conninfo()) as connection:
            with connection.cursor(name=f"transformer_dataset_rows_{uuid.uuid4().hex}") as cursor:
                cursor.execute(query, parameters)
                while rows := cursor.fetchmany(FETCH_SIZE):
                    yield from rows
    except psycopg.Error as error:
        raise TransformerDatasetError("transformer_dataset_database_failed") from error


def tokenize_rows(
    rows: Iterable[tuple[str, str]], tokenizer: DatasetTokenizer
) -> Iterator[dict[str, Any]]:
    """Batch-tokenize source rows and yield no raw text or row identity."""

    text_batch: list[str] = []
    label_batch: list[str] = []

    def consume_batch() -> Iterator[dict[str, Any]]:
        if not text_batch:
            return
        try:
            encoded = tokenizer(
                text_batch,
                add_special_tokens=True,
                padding=False,
                truncation=True,
                max_length=MAXIMUM_LENGTH,
                return_attention_mask=True,
                return_token_type_ids=True,
                verbose=False,
            )
        except (TypeError, ValueError, RuntimeError) as error:
            raise TransformerDatasetError("transformer_dataset_tokenization_failed") from error
        required = ("input_ids", "attention_mask")
        if any(key not in encoded for key in required):
            raise TransformerDatasetError("transformer_dataset_tokenization_fields_missing")
        if any(len(encoded[key]) != len(text_batch) for key in required):
            raise TransformerDatasetError("transformer_dataset_tokenization_count_mismatch")
        if "token_type_ids" in encoded and len(encoded["token_type_ids"]) != len(text_batch):
            raise TransformerDatasetError("transformer_dataset_tokenization_count_mismatch")
        for index, label in enumerate(label_batch):
            feature = {
                "input_ids": list(encoded["input_ids"][index]),
                "attention_mask": list(encoded["attention_mask"][index]),
                "labels": LABEL_TO_ID[label],
            }
            if "token_type_ids" in encoded:
                feature["token_type_ids"] = list(encoded["token_type_ids"][index])
            _validate_unpadded_feature(feature)
            yield feature
        text_batch.clear()
        label_batch.clear()

    for narrative, label in rows:
        if not isinstance(narrative, str) or not narrative.strip():
            raise TransformerDatasetError("transformer_dataset_source_row_invalid")
        if label not in LABEL_TO_ID:
            raise TransformerDatasetError("transformer_dataset_source_taxonomy_invalid")
        text_batch.append(narrative)
        label_batch.append(label)
        if len(text_batch) == TOKENIZE_BATCH_SIZE:
            yield from consume_batch()
    yield from consume_batch()


def collate_dynamic(
    features: Sequence[Mapping[str, Any]],
    tokenizer: DatasetTokenizer,
    *,
    return_tensors: str,
) -> Mapping[str, Any]:
    """Pad one caller batch to its longest sequence, rounded to a multiple of eight."""

    if not features:
        raise TransformerDatasetError("transformer_dataset_collation_empty")
    normalized = [dict(feature) for feature in features]
    for feature in normalized:
        _validate_unpadded_feature(feature)
    try:
        batch = tokenizer.pad(
            normalized,
            padding=True,
            pad_to_multiple_of=PAD_TO_MULTIPLE_OF,
            return_tensors=return_tensors,
            verbose=False,
        )
    except (TypeError, ValueError, RuntimeError) as error:
        raise TransformerDatasetError("transformer_dataset_collation_failed") from error
    _validate_collated_batch(batch, expected_batch_size=len(features))
    return batch


def buffered_shuffle[T](items: Iterable[T], *, buffer_size: int, seed: int) -> Iterator[T]:
    """Shuffle a stream reproducibly with bounded memory and no resampling."""

    if isinstance(buffer_size, bool) or not isinstance(buffer_size, int) or buffer_size < 2:
        raise TransformerDatasetError("transformer_dataset_shuffle_buffer_invalid")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise TransformerDatasetError("transformer_dataset_shuffle_seed_invalid")
    generator = random.Random(seed)
    buffer: list[T] = []
    for item in items:
        if len(buffer) < buffer_size:
            buffer.append(item)
            continue
        index = generator.randrange(len(buffer))
        yield buffer[index]
        buffer[index] = item
    while buffer:
        yield buffer.pop(generator.randrange(len(buffer)))


def validate_split_stream(
    rows: Iterable[tuple[str, str]],
    tokenizer: DatasetTokenizer,
    *,
    expected_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Consume one canonical split and verify tokenization and collation invariants."""

    if set(expected_counts) != set(LABELS):
        raise TransformerDatasetError("transformer_dataset_expected_taxonomy_invalid")
    counts: Counter[str] = Counter()
    example_count = 0
    collation_batch_count = 0
    minimum_unpadded: int | None = None
    maximum_unpadded: int | None = None
    minimum_padded: int | None = None
    maximum_padded: int | None = None
    collation_batch: list[Mapping[str, Any]] = []

    def consume_collation_batch() -> None:
        nonlocal collation_batch_count, minimum_padded, maximum_padded
        if not collation_batch:
            return
        padded = collate_dynamic(collation_batch, tokenizer, return_tensors="np")
        padded_length = int(padded["input_ids"].shape[1])
        collation_batch_count += 1
        minimum_padded = (
            padded_length if minimum_padded is None else min(minimum_padded, padded_length)
        )
        maximum_padded = (
            padded_length if maximum_padded is None else max(maximum_padded, padded_length)
        )
        collation_batch.clear()

    for feature in tokenize_rows(rows, tokenizer):
        label = ID_TO_LABEL[feature["labels"]]
        counts[label] += 1
        example_count += 1
        length = len(feature["input_ids"])
        minimum_unpadded = length if minimum_unpadded is None else min(minimum_unpadded, length)
        maximum_unpadded = length if maximum_unpadded is None else max(maximum_unpadded, length)
        collation_batch.append(feature)
        if len(collation_batch) == COLLATION_CHECK_BATCH_SIZE:
            consume_collation_batch()
    consume_collation_batch()

    if dict(counts) != dict(expected_counts):
        raise TransformerDatasetError("transformer_dataset_source_counts_do_not_reconcile")
    if None in (minimum_unpadded, maximum_unpadded, minimum_padded, maximum_padded):
        raise TransformerDatasetError("transformer_dataset_split_empty")
    return {
        "record_count": example_count,
        "class_counts": {label: counts[label] for label in LABELS},
        "collation_batch_count": collation_batch_count,
        "minimum_unpadded_length": minimum_unpadded,
        "maximum_unpadded_length": maximum_unpadded,
        "minimum_padded_length": minimum_padded,
        "maximum_padded_length": maximum_padded,
        "counts_reconcile": True,
    }


def _validate_unpadded_feature(feature: Mapping[str, Any]) -> None:
    required = {"input_ids", "attention_mask", "labels"}
    if not required.issubset(feature) or not set(feature).issubset(required | {"token_type_ids"}):
        raise TransformerDatasetError("transformer_dataset_feature_fields_invalid")
    input_ids = feature["input_ids"]
    attention_mask = feature["attention_mask"]
    if not isinstance(input_ids, Sequence) or isinstance(input_ids, (str, bytes)):
        raise TransformerDatasetError("transformer_dataset_feature_invalid")
    if not input_ids or len(input_ids) > MAXIMUM_LENGTH or len(attention_mask) != len(input_ids):
        raise TransformerDatasetError("transformer_dataset_feature_length_invalid")
    if any(value != 1 for value in attention_mask):
        raise TransformerDatasetError("transformer_dataset_stored_padding_forbidden")
    if "token_type_ids" in feature and len(feature["token_type_ids"]) != len(input_ids):
        raise TransformerDatasetError("transformer_dataset_feature_length_invalid")
    label_id = feature["labels"]
    if isinstance(label_id, bool) or not isinstance(label_id, int) or label_id not in ID_TO_LABEL:
        raise TransformerDatasetError("transformer_dataset_label_id_invalid")


def _validate_collated_batch(batch: Mapping[str, Any], *, expected_batch_size: int) -> None:
    required = {"input_ids", "attention_mask", "labels"}
    if not required.issubset(batch):
        raise TransformerDatasetError("transformer_dataset_collation_fields_missing")
    input_shape = tuple(batch["input_ids"].shape)
    mask_shape = tuple(batch["attention_mask"].shape)
    label_shape = tuple(batch["labels"].shape)
    if len(input_shape) != 2 or input_shape != mask_shape:
        raise TransformerDatasetError("transformer_dataset_collation_shape_invalid")
    if input_shape[0] != expected_batch_size or label_shape != (expected_batch_size,):
        raise TransformerDatasetError("transformer_dataset_collation_shape_invalid")
    padded_length = int(input_shape[1])
    if padded_length > MAXIMUM_LENGTH or padded_length % PAD_TO_MULTIPLE_OF:
        raise TransformerDatasetError("transformer_dataset_collation_length_invalid")


def _validate_tokenizer(tokenizer: DatasetTokenizer, bundle: TokenizerBundle) -> None:
    if not tokenizer.is_fast or tokenizer.vocab_size <= 0:
        raise TransformerDatasetError("transformer_dataset_tokenizer_invalid")
    if bundle.max_position_embeddings < MAXIMUM_LENGTH:
        raise TransformerDatasetError("transformer_dataset_maximum_length_unsupported")


def _validate_split(split: str) -> None:
    if split not in ALLOWED_SPLITS:
        raise TransformerDatasetError("transformer_dataset_split_forbidden")


def _load_pinned_dataset_tokenizer(root: Path) -> TokenizerBundle:
    return load_pinned_tokenizer(root)


def _software_versions() -> dict[str, str]:
    try:
        return {
            "python": platform.python_version(),
            "transformers": version("transformers"),
            "tokenizers": version("tokenizers"),
            "huggingface_hub": version("huggingface-hub"),
        }
    except ImportError as error:
        raise TransformerDatasetError("transformer_dataset_dependency_missing") from error


def _load_split_manifest(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    resolved = path.resolve()
    if resolved.parent != (root / "data" / "manifests" / "cfpb" / "splits").resolve():
        raise TransformerDatasetError("unsafe_split_manifest_path")
    try:
        encoded = resolved.read_bytes()
        manifest = json.loads(encoded)
        schema = json.loads(SPLIT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerDatasetError("transformer_dataset_split_manifest_unreadable") from error
    if not isinstance(manifest, dict):
        raise TransformerDatasetError("transformer_dataset_split_manifest_schema_invalid")
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)
    )
    if errors:
        raise TransformerDatasetError(
            "transformer_dataset_split_manifest_schema_invalid", issue_count=len(errors)
        )
    return manifest, encoded


def _report_path(root: Path, run_id: str) -> Path:
    return (
        root
        / "data"
        / "evaluations"
        / "cfpb"
        / "transformer-dataset"
        / f"{run_id}-{REPORT_VERSION}.json"
    )


def _load_existing_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerDatasetError("transformer_dataset_report_unreadable") from error
    if not isinstance(report, dict):
        raise TransformerDatasetError("transformer_dataset_report_schema_invalid")
    _validate_report(report)
    return report


def _validate_report(report: Mapping[str, Any]) -> None:
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise TransformerDatasetError(
            "transformer_dataset_report_schema_invalid", issue_count=len(errors)
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
        raise TransformerDatasetError("transformer_dataset_report_write_failed") from error
    finally:
        temporary.unlink(missing_ok=True)
