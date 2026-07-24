"""Approved MiniLM training configuration and non-persistent smoke workflow."""

from __future__ import annotations

import gc
import json
import math
import os
import random
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from itertools import islice
from pathlib import Path
from typing import Any

import numpy as np
import psycopg

from complaint_triage.analytical_population import POPULATION_VERSION
from complaint_triage.db import DatabaseSettings
from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.temporal_split import SPLIT_SCHEMA_PATH, SPLIT_VERSION
from complaint_triage.transformer_dataset import (
    ID_TO_LABEL,
    LABEL_TO_ID,
    LABELS,
    MAXIMUM_LENGTH,
    stream_collated_batches,
)
from complaint_triage.transformer_token_profile import (
    MODEL_ID,
    MODEL_REVISION,
    TransformerTokenProfileError,
    load_pinned_tokenizer,
)

RANDOM_SEED = 42
EFFECTIVE_BATCH_SIZE = 32
LEARNING_RATE = 2e-5
WEIGHT_DECAY = 0.01
ADAM_BETAS = (0.9, 0.999)
ADAM_EPSILON = 1e-8
MAX_GRADIENT_NORM = 1.0
WARMUP_RATIO = 0.06
SMOKE_ROWS_PER_CLASS = 100
SMOKE_OPTIMIZER_STEPS = 20
EXPECTED_TORCH_VERSION = "2.13.0+cu130"


@dataclass(frozen=True)
class BatchConfiguration:
    per_device_batch_size: int
    gradient_accumulation_steps: int
    gradient_checkpointing: bool

    def __post_init__(self) -> None:
        if self.per_device_batch_size * self.gradient_accumulation_steps != EFFECTIVE_BATCH_SIZE:
            raise ValueError("batch configuration must preserve effective batch size")


BATCH_CONFIGURATIONS = (
    BatchConfiguration(16, 2, False),
    BatchConfiguration(8, 4, False),
    BatchConfiguration(4, 8, True),
)


class BatchProbeOutOfMemory(Exception):
    """Expected signal allowing the approved hardware-only fallback."""


class TransformerTrainingError(Exception):
    """A controlled training failure containing no source row values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_transformer_training_error(error: TransformerTrainingError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "complaint_ids_logged": False,
            "token_ids_logged": False,
            "row_values_in_output": False,
        },
    }


def square_root_balanced_weights(class_counts: Mapping[str, int]) -> tuple[float, ...]:
    """Return ADR 0013 weights in stable label-ID order."""

    if set(class_counts) != set(LABELS):
        raise TransformerTrainingError("transformer_training_class_counts_invalid")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in class_counts.values()
    ):
        raise TransformerTrainingError("transformer_training_class_counts_invalid")
    total = sum(class_counts.values())
    class_count = len(class_counts)
    return tuple(math.sqrt(total / (class_count * class_counts[label])) for label in LABELS)


def select_batch_configuration(
    probe: Callable[[BatchConfiguration], Mapping[str, Any]],
) -> tuple[BatchConfiguration, Mapping[str, Any], list[dict[str, Any]]]:
    """Choose the first hardware-feasible configuration without validation data."""

    attempts: list[dict[str, Any]] = []
    for configuration in BATCH_CONFIGURATIONS:
        try:
            result = probe(configuration)
        except BatchProbeOutOfMemory:
            attempts.append({**asdict(configuration), "status": "cuda_out_of_memory"})
            continue
        attempts.append({**asdict(configuration), "status": "passed"})
        return configuration, result, attempts
    raise TransformerTrainingError("transformer_training_no_batch_configuration_fits")


def smoke_transformer_training(
    split_manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
) -> dict[str, Any]:
    """Run synthetic memory and bounded training-only integration smokes."""

    root = repository_root.resolve()
    manifest = _load_split_manifest(split_manifest_path, root)
    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")
    _set_reproducibility()
    torch = _import_torch()
    _validate_hardware(torch)
    try:
        tokenizer_bundle = load_pinned_tokenizer(root)
    except TransformerTokenProfileError as error:
        raise TransformerTrainingError("transformer_training_tokenizer_load_failed") from error
    tokenizer = tokenizer_bundle.tokenizer
    class_weights = square_root_balanced_weights(manifest["class_counts_by_split"]["train"])

    def probe(configuration: BatchConfiguration) -> Mapping[str, Any]:
        return _synthetic_batch_probe(root, configuration, class_weights, torch)

    selected, probe_result, attempts = select_batch_configuration(probe)
    rows = list(iter_training_smoke_rows(manifest, database_settings))
    _reconcile_smoke_rows(rows)
    integration = _run_training_integration_smoke(
        root,
        manifest,
        database_settings,
        tokenizer,
        rows,
        selected,
        class_weights,
        torch,
    )
    return {
        "status": "ok",
        "mode": "synthetic_memory_and_training_only_integration_smoke",
        "model": {"model_id": MODEL_ID, "revision": MODEL_REVISION, "maximum_length": 384},
        "hardware": {
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            "device": torch.cuda.get_device_name(0),
            "compute_capability": list(torch.cuda.get_device_capability(0)),
            "mixed_precision": "fp16",
        },
        "batch_selection": {
            "effective_batch_size": EFFECTIVE_BATCH_SIZE,
            "attempts": attempts,
            "selected": asdict(selected),
            "synthetic_peak_cuda_bytes": probe_result["peak_cuda_bytes"],
            "synthetic_loss_finite": True,
        },
        "integration": integration,
        "checks": {
            "training_only": True,
            "validation_accessed": False,
            "test_accessed": False,
            "model_revision_pinned": True,
            "safetensors_required": True,
            "class_weights_training_defined": True,
            "loss_finite": True,
            "artifact_written": False,
            "report_written": False,
        },
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_token_ids": False,
        },
    }


def load_pinned_sequence_classifier(root: Path, *, auto_model_class: Any | None = None) -> Any:
    """Load the approved classifier exclusively from the immutable safetensors revision."""

    if auto_model_class is None:
        try:
            from transformers import AutoModelForSequenceClassification
        except ImportError as error:
            raise TransformerTrainingError("transformer_training_dependency_missing") from error
        auto_model_class = AutoModelForSequenceClassification
    try:
        model = auto_model_class.from_pretrained(
            MODEL_ID,
            revision=MODEL_REVISION,
            cache_dir=root / "data" / "model_cache" / "huggingface",
            use_safetensors=True,
            trust_remote_code=False,
            num_labels=len(LABELS),
            id2label=ID_TO_LABEL,
            label2id=LABEL_TO_ID,
        )
    except (OSError, ValueError) as error:
        raise TransformerTrainingError("transformer_training_model_load_failed") from error
    if getattr(model.config, "_commit_hash", None) != MODEL_REVISION:
        raise TransformerTrainingError("transformer_training_model_revision_mismatch")
    return model


def iter_training_smoke_rows(
    manifest: Mapping[str, Any], settings: DatabaseSettings
) -> Iterable[tuple[str, str]]:
    """Read exactly 100 stable training rows per class and no other split."""

    query = """
        WITH ranked AS (
            SELECT s.narrative, p.target_product,
                   row_number() OVER (
                       PARTITION BY p.target_product
                       ORDER BY o.raw_batch_id, o.source_row_ordinal
                   ) AS class_row
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
        )
        SELECT narrative, target_product
        FROM ranked
        WHERE class_row <= %s
        ORDER BY target_product, class_row
    """
    parameters = (
        manifest["run_id"],
        SPLIT_VERSION,
        POPULATION_VERSION,
        SMOKE_ROWS_PER_CLASS,
    )
    try:
        with psycopg.connect(settings.psycopg_conninfo()) as connection:
            with connection.cursor(name=f"transformer_smoke_rows_{uuid.uuid4().hex}") as cursor:
                cursor.execute(query, parameters)
                while rows := cursor.fetchmany(1_000):
                    yield from rows
    except psycopg.Error as error:
        raise TransformerTrainingError("transformer_training_database_failed") from error


def _synthetic_batch_probe(
    root: Path,
    configuration: BatchConfiguration,
    class_weights: tuple[float, ...],
    torch: Any,
) -> Mapping[str, Any]:
    _release_cuda(torch)
    out_of_memory = False
    try:
        result = _execute_synthetic_batch_probe(root, configuration, class_weights, torch)
    except torch.OutOfMemoryError:
        out_of_memory = True
    finally:
        _release_cuda(torch)
    if out_of_memory:
        raise BatchProbeOutOfMemory
    return result


def _execute_synthetic_batch_probe(
    root: Path,
    configuration: BatchConfiguration,
    class_weights: tuple[float, ...],
    torch: Any,
) -> Mapping[str, Any]:
    """Execute one probe in an isolated frame so CUDA tensors are releasable."""

    model = load_pinned_sequence_classifier(root).to("cuda")
    if configuration.gradient_checkpointing:
        model.gradient_checkpointing_enable()
    model.train()
    optimizer = _build_optimizer(model, torch)
    scaler = torch.amp.GradScaler("cuda")
    weight_tensor = torch.tensor(class_weights, dtype=torch.float32, device="cuda")
    loss_function = torch.nn.CrossEntropyLoss(weight=weight_tensor)
    torch.cuda.reset_peak_memory_stats()
    optimizer.zero_grad(set_to_none=True)
    last_loss = None
    for micro_step in range(configuration.gradient_accumulation_steps):
        generator = torch.Generator(device="cuda")
        generator.manual_seed(RANDOM_SEED + micro_step)
        input_ids = torch.randint(
            999,
            30_000,
            (configuration.per_device_batch_size, MAXIMUM_LENGTH),
            generator=generator,
            device="cuda",
        )
        attention_mask = torch.ones_like(input_ids)
        token_type_ids = torch.zeros_like(input_ids)
        labels = torch.arange(configuration.per_device_batch_size, device="cuda") % len(LABELS)
        with torch.amp.autocast("cuda", dtype=torch.float16):
            logits = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                token_type_ids=token_type_ids,
            ).logits
            loss = loss_function(logits.float(), labels)
            scaled_loss = loss / configuration.gradient_accumulation_steps
        if not torch.isfinite(loss):
            raise TransformerTrainingError("transformer_training_nonfinite_loss")
        scaler.scale(scaled_loss).backward()
        last_loss = loss
    scaler.unscale_(optimizer)
    torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_GRADIENT_NORM)
    scaler.step(optimizer)
    scaler.update()
    return {
        "peak_cuda_bytes": int(torch.cuda.max_memory_allocated()),
        "loss_finite": bool(last_loss is not None and torch.isfinite(last_loss)),
    }


def _run_training_integration_smoke(
    root: Path,
    manifest: Mapping[str, Any],
    settings: DatabaseSettings,
    tokenizer: Any,
    rows: list[tuple[str, str]],
    configuration: BatchConfiguration,
    class_weights: tuple[float, ...],
    torch: Any,
) -> dict[str, Any]:
    _set_reproducibility()
    model = load_pinned_sequence_classifier(root).to("cuda")
    if configuration.gradient_checkpointing:
        model.gradient_checkpointing_enable()
    model.train()
    optimizer = _build_optimizer(model, torch)
    scheduler = _build_linear_scheduler(optimizer, SMOKE_OPTIMIZER_STEPS, torch)
    scaler = torch.amp.GradScaler("cuda")
    weight_tensor = torch.tensor(class_weights, dtype=torch.float32, device="cuda")
    loss_function = torch.nn.CrossEntropyLoss(weight=weight_tensor)

    def smoke_loader(_manifest: Mapping[str, Any], _settings: DatabaseSettings, split: str):
        if split != "train":
            raise TransformerTrainingError("transformer_training_smoke_split_forbidden")
        return iter(rows)

    batches = stream_collated_batches(
        manifest,
        settings,
        "train",
        tokenizer,
        batch_size=configuration.per_device_batch_size,
        return_tensors="pt",
        epoch=0,
        row_loader=smoke_loader,
    )
    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    rows_processed = 0
    optimizer_steps = 0
    try:
        while optimizer_steps < SMOKE_OPTIMIZER_STEPS:
            group = list(islice(batches, configuration.gradient_accumulation_steps))
            if not group:
                break
            optimizer.zero_grad(set_to_none=True)
            for batch in group:
                labels = batch["labels"].to("cuda", non_blocking=True)
                inputs = {
                    key: value.to("cuda", non_blocking=True)
                    for key, value in batch.items()
                    if key != "labels"
                }
                with torch.amp.autocast("cuda", dtype=torch.float16):
                    logits = model(**inputs).logits
                    loss = loss_function(logits.float(), labels)
                    scaled_loss = loss / len(group)
                if not torch.isfinite(loss):
                    raise TransformerTrainingError("transformer_training_nonfinite_loss")
                scaler.scale(scaled_loss).backward()
                rows_processed += int(labels.shape[0])
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_GRADIENT_NORM)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            optimizer_steps += 1
        if optimizer_steps != SMOKE_OPTIMIZER_STEPS:
            raise TransformerTrainingError(
                "transformer_training_smoke_steps_incomplete", observed_steps=optimizer_steps
            )
        return {
            "source_record_count": len(rows),
            "rows_processed": rows_processed,
            "optimizer_steps": optimizer_steps,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "peak_cuda_bytes": int(torch.cuda.max_memory_allocated()),
            "loss_finite": True,
            "validation_accessed": False,
            "test_accessed": False,
        }
    finally:
        del model, optimizer, scheduler, scaler, weight_tensor, loss_function
        _release_cuda(torch)


def _build_optimizer(model: Any, torch: Any) -> Any:
    return torch.optim.AdamW(
        model.parameters(),
        lr=LEARNING_RATE,
        betas=ADAM_BETAS,
        eps=ADAM_EPSILON,
        weight_decay=WEIGHT_DECAY,
        fused=False,
    )


def _build_linear_scheduler(optimizer: Any, total_steps: int, torch: Any) -> Any:
    warmup_steps = max(1, math.ceil(total_steps * WARMUP_RATIO))

    def multiplier(step: int) -> float:
        if step < warmup_steps:
            return step / warmup_steps
        return max(0.0, (total_steps - step) / max(1, total_steps - warmup_steps))

    return torch.optim.lr_scheduler.LambdaLR(optimizer, multiplier)


def _set_reproducibility() -> None:
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    try:
        torch = _import_torch()
    except TransformerTrainingError:
        return
    torch.manual_seed(RANDOM_SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(RANDOM_SEED)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)


def _validate_hardware(torch: Any) -> None:
    if torch.__version__ != EXPECTED_TORCH_VERSION:
        raise TransformerTrainingError(
            "transformer_training_torch_version_mismatch", observed=torch.__version__
        )
    if not torch.cuda.is_available() or torch.version.cuda != "13.0":
        raise TransformerTrainingError("transformer_training_cuda_unavailable")
    if torch.cuda.get_device_capability(0) != (12, 0):
        raise TransformerTrainingError("transformer_training_gpu_capability_mismatch")


def _import_torch() -> Any:
    try:
        import torch
    except ImportError as error:
        raise TransformerTrainingError("transformer_training_dependency_missing") from error
    return torch


def _release_cuda(torch: Any) -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _reconcile_smoke_rows(rows: list[tuple[str, str]]) -> None:
    expected = {label: SMOKE_ROWS_PER_CLASS for label in LABELS}
    counts: Counter[str] = Counter()
    for narrative, label in rows:
        if not isinstance(narrative, str) or not narrative.strip() or label not in LABEL_TO_ID:
            raise TransformerTrainingError("transformer_training_smoke_source_invalid")
        counts[label] += 1
    if dict(counts) != expected:
        raise TransformerTrainingError("transformer_training_smoke_counts_do_not_reconcile")


def _load_split_manifest(path: Path, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if resolved.parent != (root / "data" / "manifests" / "cfpb" / "splits").resolve():
        raise TransformerTrainingError("unsafe_split_manifest_path")
    try:
        encoded = resolved.read_bytes()
        manifest = json.loads(encoded)
        schema = json.loads(SPLIT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerTrainingError("transformer_training_split_manifest_unreadable") from error
    if not isinstance(manifest, dict):
        raise TransformerTrainingError("transformer_training_split_manifest_invalid")
    from jsonschema import Draft202012Validator, FormatChecker

    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)
    )
    if errors:
        raise TransformerTrainingError(
            "transformer_training_split_manifest_invalid", issue_count=len(errors)
        )
    return manifest
