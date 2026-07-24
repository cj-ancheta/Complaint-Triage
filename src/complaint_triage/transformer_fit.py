"""Governed validation-only MiniLM fitting and aggregate experiment tracking."""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import random
import re
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import version
from itertools import islice
from pathlib import Path
from typing import Any

import numpy as np
from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.db import DatabaseSettings
from complaint_triage.live_extraction import read_git_lineage
from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.temporal_split import SPLIT_VERSION
from complaint_triage.transformer_dataset import (
    LABELS,
    TransformerDatasetError,
    stream_collated_batches,
)
from complaint_triage.transformer_token_profile import (
    MODEL_ID,
    MODEL_REVISION,
    TransformerTokenProfileError,
    load_pinned_tokenizer,
)
from complaint_triage.transformer_training import (
    ADAM_BETAS,
    ADAM_EPSILON,
    LEARNING_RATE,
    MAX_GRADIENT_NORM,
    WARMUP_RATIO,
    WEIGHT_DECAY,
    BatchConfiguration,
    TransformerTrainingError,
    _build_linear_scheduler,
    _build_optimizer,
    _import_torch,
    _load_split_manifest,
    _release_cuda,
    _set_reproducibility,
    _synthetic_batch_probe,
    _validate_hardware,
    load_pinned_sequence_classifier,
    select_batch_configuration,
    square_root_balanced_weights,
)

REPORT_VERSION = "transformer-minilm-selection-1.0.0"
ARTIFACT_VERSION = "transformer-minilm-1.0.0"
RESUME_VERSION = "transformer-minilm-resume-1.0.0"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-transformer-training.schema.json"
RETENTION = "local_only_governed_until_2026-11-19"
MAXIMUM_EPOCHS = 3
MINIMUM_MACRO_F1_IMPROVEMENT = 0.001
EARLY_STOPPING_PATIENCE = 1
PROGRESS_INTERVAL_STEPS = 1_000
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

LineageReader = Callable[[Path], tuple[str, bool]]
Clock = Callable[[], datetime]
ProgressReporter = Callable[[Mapping[str, Any]], None]


class TransformerFitError(Exception):
    """A controlled full-fit failure containing no source row values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_transformer_fit_error(error: TransformerFitError) -> dict[str, Any]:
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


def train_transformer(
    split_manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
    lineage_reader: LineageReader = read_git_lineage,
    clock: Clock = lambda: datetime.now(UTC),
    progress: ProgressReporter | None = None,
) -> dict[str, Any]:
    """Fit one approved MiniLM candidate and select an epoch on validation only."""

    root = repository_root.resolve()
    manifest_path = split_manifest_path.resolve()
    try:
        manifest = _load_split_manifest(manifest_path, root)
    except TransformerTrainingError as error:
        raise TransformerFitError(error.code, **error.details) from error
    manifest_bytes = _read_manifest_bytes(manifest_path)
    split_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    report_path = _report_path(root, manifest["run_id"])
    artifact_directory = _artifact_directory(root, manifest["run_id"])
    if report_path.exists():
        report = _load_existing_report(report_path)
        if report["source"]["split_manifest_sha256"] != split_sha256:
            raise TransformerFitError("transformer_fit_report_identity_conflict")
        _verify_report_artifacts(root, report)
        return report

    commit_sha, clean = lineage_reader(root)
    if not SHA40_PATTERN.fullmatch(commit_sha) or not clean:
        raise TransformerFitError("transformer_fit_requires_clean_commit")
    trained_at = clock()
    if trained_at.tzinfo is None or trained_at.utcoffset() != UTC.utcoffset(trained_at):
        raise TransformerFitError("transformer_fit_clock_invalid")

    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")
    torch = _import_fit_torch()
    _validate_fit_hardware(torch)
    _set_reproducibility()
    try:
        tokenizer = load_pinned_tokenizer(root).tokenizer
    except TransformerTokenProfileError as error:
        raise TransformerFitError("transformer_fit_tokenizer_load_failed") from error
    class_weights = square_root_balanced_weights(manifest["class_counts_by_split"]["train"])

    def probe(configuration: BatchConfiguration) -> Mapping[str, Any]:
        return _synthetic_batch_probe(root, configuration, class_weights, torch)

    try:
        configuration, probe_result, probe_attempts = select_batch_configuration(probe)
    except TransformerTrainingError as error:
        raise TransformerFitError(error.code, **error.details) from error
    _emit(
        progress,
        {
            "event": "transformer_fit_started",
            "maximum_epochs": MAXIMUM_EPOCHS,
            "per_device_batch_size": configuration.per_device_batch_size,
            "gradient_accumulation_steps": configuration.gradient_accumulation_steps,
            "test_accessed": False,
        },
    )

    train_count = int(manifest["split_counts"]["train"])
    optimizer_steps_per_epoch = _optimizer_steps_per_epoch(train_count, configuration)
    total_optimizer_steps = optimizer_steps_per_epoch * MAXIMUM_EPOCHS
    model, optimizer, scheduler, scaler, history, start_epoch, monitor_best = _initialize_or_resume(
        root,
        artifact_directory,
        split_sha256,
        commit_sha,
        configuration,
        class_weights,
        total_optimizer_steps,
        torch,
    )
    weight_tensor = torch.tensor(class_weights, dtype=torch.float32, device="cuda")
    loss_function = torch.nn.CrossEntropyLoss(weight=weight_tensor)
    selected_epoch = select_epoch(history)["epoch"] if history else None
    non_improving_epochs = 0
    if history:
        non_improving_epochs = int(history[-1]["early_stopping"]["non_improving_epochs"])
    peak_cuda_bytes = int(probe_result["peak_cuda_bytes"])
    stopped_early = non_improving_epochs >= EARLY_STOPPING_PATIENCE
    try:
        for epoch in range(start_epoch, MAXIMUM_EPOCHS + 1):
            if non_improving_epochs >= EARLY_STOPPING_PATIENCE:
                stopped_early = True
                break
            training = _train_epoch(
                model,
                optimizer,
                scheduler,
                scaler,
                loss_function,
                manifest,
                database_settings,
                tokenizer,
                configuration,
                epoch,
                torch,
                progress,
            )
            validation = _evaluate_validation(
                model,
                loss_function,
                manifest,
                database_settings,
                tokenizer,
                configuration,
                torch,
            )
            _reconcile_epoch(training, validation, manifest, optimizer_steps_per_epoch)
            peak_cuda_bytes = max(
                peak_cuda_bytes,
                int(training["peak_cuda_bytes"]),
                int(validation["peak_cuda_bytes"]),
            )
            macro_f1 = float(validation["metrics"]["macro_f1"])
            monitor_best, non_improving_epochs, improved = update_early_stopping(
                macro_f1, monitor_best, non_improving_epochs
            )
            epoch_result = {
                "epoch": epoch,
                "training": training,
                "validation": validation,
                "early_stopping": {
                    "minimum_improvement_met": improved,
                    "monitored_best_macro_f1": monitor_best,
                    "non_improving_epochs": non_improving_epochs,
                },
            }
            history.append(epoch_result)
            newly_selected = int(select_epoch(history)["epoch"])
            if newly_selected != selected_epoch:
                _save_safetensors_model(model, artifact_directory / "best-model.safetensors", torch)
                selected_epoch = newly_selected
            _save_latest_checkpoint(
                root,
                artifact_directory,
                model,
                optimizer,
                scheduler,
                scaler,
                epoch,
                history,
                monitor_best,
                split_sha256,
                commit_sha,
                configuration,
                class_weights,
                torch,
            )
            _emit(
                progress,
                {
                    "event": "transformer_fit_epoch_completed",
                    "epoch": epoch,
                    "train_record_count": training["record_count"],
                    "validation_record_count": validation["record_count"],
                    "validation_macro_f1": macro_f1,
                    "validation_worst_class_recall": validation["metrics"]["worst_class_recall"],
                    "selected_epoch": selected_epoch,
                    "test_accessed": False,
                },
            )
            if non_improving_epochs >= EARLY_STOPPING_PATIENCE:
                stopped_early = True
                break
    except TransformerDatasetError as error:
        raise TransformerFitError(error.code, **error.details) from error
    except torch.OutOfMemoryError as error:
        raise TransformerFitError("transformer_fit_cuda_out_of_memory") from error
    finally:
        del model, optimizer, scheduler, scaler, weight_tensor, loss_function
        _release_cuda(torch)

    if not history or selected_epoch is None:
        raise TransformerFitError("transformer_fit_no_eligible_epoch")
    selected = select_epoch(history)
    artifacts = _collect_artifacts(root, artifact_directory)
    report = _build_report(
        manifest,
        split_sha256,
        commit_sha,
        trained_at,
        configuration,
        probe_attempts,
        class_weights,
        optimizer_steps_per_epoch,
        history,
        selected,
        stopped_early,
        peak_cuda_bytes,
        artifacts,
        torch,
    )
    _validate_report(report)
    _atomic_json(report_path, report)
    _emit(
        progress,
        {
            "event": "transformer_fit_completed",
            "completed_epochs": len(history),
            "selected_epoch": selected_epoch,
            "test_accessed": False,
        },
    )
    return report


def select_epoch(epochs: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Apply the accepted ordered validation selection rule."""

    if not epochs:
        raise TransformerFitError("transformer_fit_no_eligible_epoch")
    return min(
        epochs,
        key=lambda item: (
            -float(item["validation"]["metrics"]["macro_f1"]),
            -float(item["validation"]["metrics"]["worst_class_recall"]),
            -float(item["validation"]["metrics"]["weighted_f1"]),
            int(item["epoch"]),
        ),
    )


def update_early_stopping(
    macro_f1: float, monitor_best: float | None, non_improving_epochs: int
) -> tuple[float, int, bool]:
    """Apply the fixed 0.001 minimum improvement and patience-one rule."""

    if not math.isfinite(macro_f1) or not 0 <= macro_f1 <= 1:
        raise TransformerFitError("transformer_fit_macro_f1_invalid")
    improved = monitor_best is None or (macro_f1 >= monitor_best + MINIMUM_MACRO_F1_IMPROVEMENT)
    if improved:
        return macro_f1, 0, True
    return float(monitor_best), non_improving_epochs + 1, False


def metrics_from_confusion(
    confusion: Sequence[Sequence[int]], *, top_2_correct: int, record_count: int
) -> dict[str, Any]:
    """Derive the declared aggregate metrics without retaining predictions."""

    matrix = np.asarray(confusion, dtype=np.int64)
    class_count = len(LABELS)
    if matrix.shape != (class_count, class_count) or np.any(matrix < 0):
        raise TransformerFitError("transformer_fit_confusion_invalid")
    if int(matrix.sum()) != record_count or not 0 <= top_2_correct <= record_count:
        raise TransformerFitError("transformer_fit_metric_counts_invalid")
    support = matrix.sum(axis=1)
    predicted = matrix.sum(axis=0)
    true_positive = np.diag(matrix)
    precision = np.divide(
        true_positive,
        predicted,
        out=np.zeros(class_count, dtype=np.float64),
        where=predicted != 0,
    )
    recall = np.divide(
        true_positive,
        support,
        out=np.zeros(class_count, dtype=np.float64),
        where=support != 0,
    )
    f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros(class_count, dtype=np.float64),
        where=(precision + recall) != 0,
    )
    per_class = {
        label: {
            "support": int(support[index]),
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
        }
        for index, label in enumerate(LABELS)
    }
    return {
        "accuracy": float(true_positive.sum() / record_count),
        "macro_f1": float(f1.mean()),
        "weighted_f1": float(np.average(f1, weights=support)),
        "worst_class_recall": float(recall.min()),
        "top_2_accuracy": float(top_2_correct / record_count),
        "per_class": per_class,
        "confusion_matrix": {
            "orientation": "rows_actual_columns_predicted",
            "labels": list(LABELS),
            "rows": matrix.tolist(),
        },
    }


def _train_epoch(
    model: Any,
    optimizer: Any,
    scheduler: Any,
    scaler: Any,
    loss_function: Any,
    manifest: Mapping[str, Any],
    settings: DatabaseSettings,
    tokenizer: Any,
    configuration: BatchConfiguration,
    epoch: int,
    torch: Any,
    progress: ProgressReporter | None,
) -> dict[str, Any]:
    model.train()
    batches = stream_collated_batches(
        manifest,
        settings,
        "train",
        tokenizer,
        batch_size=configuration.per_device_batch_size,
        return_tensors="pt",
        epoch=epoch - 1,
    )
    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    rows_processed = 0
    optimizer_steps = 0
    loss_sum = 0.0
    counts = [0] * len(LABELS)
    while group := list(islice(batches, configuration.gradient_accumulation_steps)):
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
                raise TransformerFitError("transformer_fit_nonfinite_training_loss", epoch=epoch)
            scaler.scale(scaled_loss).backward()
            batch_size = int(labels.shape[0])
            rows_processed += batch_size
            loss_sum += float(loss.detach().cpu()) * batch_size
            label_counts = torch.bincount(labels, minlength=len(LABELS)).cpu().tolist()
            counts = [left + int(right) for left, right in zip(counts, label_counts, strict=True)]
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_GRADIENT_NORM)
        scaler.step(optimizer)
        scaler.update()
        scheduler.step()
        optimizer_steps += 1
        if optimizer_steps % PROGRESS_INTERVAL_STEPS == 0:
            _emit(
                progress,
                {
                    "event": "transformer_fit_training_progress",
                    "epoch": epoch,
                    "optimizer_steps": optimizer_steps,
                    "rows_processed": rows_processed,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "test_accessed": False,
                },
            )
    return {
        "record_count": rows_processed,
        "class_counts": {label: counts[index] for index, label in enumerate(LABELS)},
        "optimizer_steps": optimizer_steps,
        "mean_loss": loss_sum / rows_processed,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "peak_cuda_bytes": int(torch.cuda.max_memory_allocated()),
        "loss_finite": True,
    }


def _evaluate_validation(
    model: Any,
    loss_function: Any,
    manifest: Mapping[str, Any],
    settings: DatabaseSettings,
    tokenizer: Any,
    configuration: BatchConfiguration,
    torch: Any,
) -> dict[str, Any]:
    model.eval()
    batches = stream_collated_batches(
        manifest,
        settings,
        "validation",
        tokenizer,
        batch_size=configuration.per_device_batch_size,
        return_tensors="pt",
        epoch=None,
    )
    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    record_count = 0
    loss_sum = 0.0
    top_2_correct = 0
    matrix = torch.zeros((len(LABELS), len(LABELS)), dtype=torch.int64, device="cuda")
    with torch.inference_mode():
        for batch in batches:
            labels = batch["labels"].to("cuda", non_blocking=True)
            inputs = {
                key: value.to("cuda", non_blocking=True)
                for key, value in batch.items()
                if key != "labels"
            }
            with torch.amp.autocast("cuda", dtype=torch.float16):
                logits = model(**inputs).logits
                loss = loss_function(logits.float(), labels)
            if not torch.isfinite(loss):
                raise TransformerFitError("transformer_fit_nonfinite_validation_loss")
            predictions = logits.argmax(dim=1)
            flattened = labels * len(LABELS) + predictions
            matrix += torch.bincount(flattened, minlength=len(LABELS) ** 2).reshape(
                len(LABELS), len(LABELS)
            )
            top_2 = logits.topk(k=2, dim=1).indices
            top_2_correct += int((top_2 == labels.unsqueeze(1)).any(dim=1).sum().cpu())
            batch_size = int(labels.shape[0])
            record_count += batch_size
            loss_sum += float(loss.detach().cpu()) * batch_size
    confusion = matrix.cpu().tolist()
    return {
        "record_count": record_count,
        "mean_loss": loss_sum / record_count,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "peak_cuda_bytes": int(torch.cuda.max_memory_allocated()),
        "loss_finite": True,
        "metrics": metrics_from_confusion(
            confusion, top_2_correct=top_2_correct, record_count=record_count
        ),
    }


def _optimizer_steps_per_epoch(train_count: int, configuration: BatchConfiguration) -> int:
    micro_batches = math.ceil(train_count / configuration.per_device_batch_size)
    return math.ceil(micro_batches / configuration.gradient_accumulation_steps)


def _reconcile_epoch(
    training: Mapping[str, Any],
    validation: Mapping[str, Any],
    manifest: Mapping[str, Any],
    expected_optimizer_steps: int,
) -> None:
    if training["record_count"] != manifest["split_counts"]["train"]:
        raise TransformerFitError("transformer_fit_train_count_mismatch")
    if training["class_counts"] != manifest["class_counts_by_split"]["train"]:
        raise TransformerFitError("transformer_fit_train_class_counts_mismatch")
    if training["optimizer_steps"] != expected_optimizer_steps:
        raise TransformerFitError("transformer_fit_optimizer_steps_mismatch")
    if validation["record_count"] != manifest["split_counts"]["validation"]:
        raise TransformerFitError("transformer_fit_validation_count_mismatch")
    observed_support = {
        label: validation["metrics"]["per_class"][label]["support"] for label in LABELS
    }
    if observed_support != manifest["class_counts_by_split"]["validation"]:
        raise TransformerFitError("transformer_fit_validation_class_counts_mismatch")


def _initialize_or_resume(
    root: Path,
    artifact_directory: Path,
    split_sha256: str,
    commit_sha: str,
    configuration: BatchConfiguration,
    class_weights: tuple[float, ...],
    total_optimizer_steps: int,
    torch: Any,
) -> tuple[Any, Any, Any, Any, list[dict[str, Any]], int, float | None]:
    _set_reproducibility()
    try:
        model = load_pinned_sequence_classifier(root).to("cuda")
    except TransformerTrainingError as error:
        raise TransformerFitError(error.code, **error.details) from error
    if configuration.gradient_checkpointing:
        model.gradient_checkpointing_enable()
    optimizer = _build_optimizer(model, torch)
    scheduler = _build_linear_scheduler(optimizer, total_optimizer_steps, torch)
    scaler = torch.amp.GradScaler("cuda")
    resume_path = artifact_directory / "latest-resume.json"
    if not resume_path.exists():
        return model, optimizer, scheduler, scaler, [], 1, None
    resume = _load_resume_manifest(
        resume_path, root, split_sha256, commit_sha, configuration, class_weights
    )
    _load_safetensors_model(model, root / resume["model"]["relative_path"], torch)
    state_path = root / resume["training_state"]["relative_path"]
    try:
        state = torch.load(state_path, map_location="cpu", weights_only=False)
    except (OSError, RuntimeError, ValueError) as error:
        raise TransformerFitError("transformer_fit_resume_state_unreadable") from error
    _validate_resume_state(state, resume)
    optimizer.load_state_dict(state["optimizer"])
    scheduler.load_state_dict(state["scheduler"])
    scaler.load_state_dict(state["scaler"])
    _restore_rng_state(state["rng"], torch)
    history = state["history"]
    return (
        model,
        optimizer,
        scheduler,
        scaler,
        history,
        int(state["completed_epoch"]) + 1,
        state["monitor_best_macro_f1"],
    )


def _save_latest_checkpoint(
    root: Path,
    directory: Path,
    model: Any,
    optimizer: Any,
    scheduler: Any,
    scaler: Any,
    completed_epoch: int,
    history: list[dict[str, Any]],
    monitor_best: float,
    split_sha256: str,
    commit_sha: str,
    configuration: BatchConfiguration,
    class_weights: tuple[float, ...],
    torch: Any,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    model_path = directory / f"latest-model-epoch-{completed_epoch}.safetensors"
    state_path = directory / f"latest-training-state-epoch-{completed_epoch}.pt"
    _save_safetensors_model(model, model_path, torch)
    state = {
        "resume_version": RESUME_VERSION,
        "completed_epoch": completed_epoch,
        "history": history,
        "monitor_best_macro_f1": monitor_best,
        "optimizer": optimizer.state_dict(),
        "scheduler": scheduler.state_dict(),
        "scaler": scaler.state_dict(),
        "rng": _capture_rng_state(torch),
    }
    _atomic_torch_save(state_path, state, torch)
    resume = {
        "resume_version": RESUME_VERSION,
        "split_manifest_sha256": split_sha256,
        "training_implementation_commit_sha": commit_sha,
        "completed_epoch": completed_epoch,
        "configuration": {
            "per_device_batch_size": configuration.per_device_batch_size,
            "gradient_accumulation_steps": configuration.gradient_accumulation_steps,
            "gradient_checkpointing": configuration.gradient_checkpointing,
        },
        "class_weights": [float(value) for value in class_weights],
        "model": _artifact_metadata(model_path, root),
        "training_state": _artifact_metadata(state_path, root),
    }
    _atomic_json(directory / "latest-resume.json", resume)
    _prune_superseded_resume_files(directory, model_path, state_path)


def _load_resume_manifest(
    path: Path,
    root: Path,
    split_sha256: str,
    commit_sha: str,
    configuration: BatchConfiguration,
    class_weights: tuple[float, ...],
) -> dict[str, Any]:
    try:
        resume = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerFitError("transformer_fit_resume_manifest_unreadable") from error
    expected_configuration = {
        "per_device_batch_size": configuration.per_device_batch_size,
        "gradient_accumulation_steps": configuration.gradient_accumulation_steps,
        "gradient_checkpointing": configuration.gradient_checkpointing,
    }
    if (
        not isinstance(resume, dict)
        or resume.get("resume_version") != RESUME_VERSION
        or resume.get("split_manifest_sha256") != split_sha256
        or resume.get("training_implementation_commit_sha") != commit_sha
        or resume.get("configuration") != expected_configuration
        or resume.get("class_weights") != [float(value) for value in class_weights]
    ):
        raise TransformerFitError("transformer_fit_resume_identity_mismatch")
    for key in ("model", "training_state"):
        _verify_artifact_metadata(root, resume.get(key), prefix="artifacts/cfpb/transformer/")
    return resume


def _validate_resume_state(state: Any, resume: Mapping[str, Any]) -> None:
    required = {
        "resume_version",
        "completed_epoch",
        "history",
        "monitor_best_macro_f1",
        "optimizer",
        "scheduler",
        "scaler",
        "rng",
    }
    if not isinstance(state, dict) or set(state) != required:
        raise TransformerFitError("transformer_fit_resume_state_invalid")
    epoch = state["completed_epoch"]
    history = state["history"]
    if (
        state["resume_version"] != RESUME_VERSION
        or epoch != resume["completed_epoch"]
        or not isinstance(epoch, int)
        or not 1 <= epoch <= MAXIMUM_EPOCHS
        or not isinstance(history, list)
        or len(history) != epoch
    ):
        raise TransformerFitError("transformer_fit_resume_state_invalid")


def _capture_rng_state(torch: Any) -> dict[str, Any]:
    return {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch_cpu": torch.get_rng_state(),
        "torch_cuda": torch.cuda.get_rng_state_all(),
    }


def _restore_rng_state(state: Mapping[str, Any], torch: Any) -> None:
    try:
        random.setstate(state["python"])
        np.random.set_state(state["numpy"])
        torch.set_rng_state(state["torch_cpu"].cpu())
        torch.cuda.set_rng_state_all(state["torch_cuda"])
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise TransformerFitError("transformer_fit_resume_rng_invalid") from error


def _save_safetensors_model(model: Any, path: Path, torch: Any) -> None:
    try:
        from safetensors.torch import save_file
    except ImportError as error:
        raise TransformerFitError("transformer_fit_dependency_missing") from error
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    state = {key: value.detach().cpu().contiguous() for key, value in model.state_dict().items()}
    try:
        save_file(
            state,
            temporary,
            metadata={
                "format": "pt",
                "model_id": MODEL_ID,
                "model_revision": MODEL_REVISION,
                "artifact_version": ARTIFACT_VERSION,
            },
        )
        os.replace(temporary, path)
    except (OSError, RuntimeError, ValueError) as error:
        raise TransformerFitError("transformer_fit_model_write_failed") from error
    finally:
        temporary.unlink(missing_ok=True)
        del state
        _release_cuda(torch)


def _load_safetensors_model(model: Any, path: Path, torch: Any) -> None:
    try:
        from safetensors.torch import load_file

        state = load_file(path, device="cuda")
        model.load_state_dict(state, strict=True)
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        raise TransformerFitError("transformer_fit_model_artifact_unreadable") from error


def _atomic_torch_save(path: Path, value: Mapping[str, Any], torch: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        torch.save(value, temporary)
        os.replace(temporary, path)
    except (OSError, RuntimeError, ValueError) as error:
        raise TransformerFitError("transformer_fit_resume_state_write_failed") from error
    finally:
        temporary.unlink(missing_ok=True)


def _artifact_metadata(path: Path, root: Path) -> dict[str, Any]:
    try:
        relative_path = path.resolve().relative_to(root.resolve()).as_posix()
        byte_count = path.stat().st_size
        digest = _sha256_file(path)
    except (OSError, ValueError) as error:
        raise TransformerFitError("transformer_fit_artifact_metadata_failed") from error
    if not relative_path.startswith("artifacts/cfpb/transformer/"):
        raise TransformerFitError("transformer_fit_artifact_path_unsafe")
    return {
        "relative_path": relative_path,
        "sha256": digest,
        "byte_count": byte_count,
        "retention": RETENTION,
    }


def _collect_artifacts(root: Path, directory: Path) -> dict[str, Any]:
    resume_path = directory / "latest-resume.json"
    try:
        resume = json.loads(resume_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerFitError("transformer_fit_resume_manifest_unreadable") from error
    if not isinstance(resume, dict):
        raise TransformerFitError("transformer_fit_resume_manifest_unreadable")
    artifacts = {
        "best_model": _artifact_metadata(directory / "best-model.safetensors", root),
        "latest_model": resume.get("model"),
        "latest_training_state": resume.get("training_state"),
        "latest_resume_manifest": _artifact_metadata(resume_path, root),
    }
    for metadata in (artifacts["latest_model"], artifacts["latest_training_state"]):
        _verify_artifact_metadata(root, metadata, prefix="artifacts/cfpb/transformer/")
    return artifacts


def _prune_superseded_resume_files(
    directory: Path, current_model: Path, current_state: Path
) -> None:
    """Remove only superseded generations after the new manifest is durable."""

    patterns = ("latest-model-epoch-*.safetensors", "latest-training-state-epoch-*.pt")
    keep = {current_model.resolve(), current_state.resolve()}
    for pattern in patterns:
        for candidate in directory.glob(pattern):
            resolved = candidate.resolve()
            if resolved.parent != directory.resolve():
                raise TransformerFitError("transformer_fit_artifact_path_unsafe")
            if resolved not in keep:
                try:
                    candidate.unlink()
                except OSError as error:
                    raise TransformerFitError("transformer_fit_checkpoint_prune_failed") from error


def _verify_report_artifacts(root: Path, report: Mapping[str, Any]) -> None:
    artifacts = report.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {
        "best_model",
        "latest_model",
        "latest_training_state",
        "latest_resume_manifest",
    }:
        raise TransformerFitError("transformer_fit_artifact_metadata_invalid")
    for metadata in artifacts.values():
        _verify_artifact_metadata(root, metadata, prefix="artifacts/cfpb/transformer/")


def _verify_artifact_metadata(root: Path, metadata: Any, *, prefix: str) -> None:
    if not isinstance(metadata, dict):
        raise TransformerFitError("transformer_fit_artifact_metadata_invalid")
    relative = metadata.get("relative_path")
    digest = metadata.get("sha256")
    size = metadata.get("byte_count")
    if (
        not isinstance(relative, str)
        or not relative.startswith(prefix)
        or not isinstance(digest, str)
        or not SHA256_PATTERN.fullmatch(digest)
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 1
    ):
        raise TransformerFitError("transformer_fit_artifact_metadata_invalid")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve() / "artifacts" / "cfpb" / "transformer")
        observed_size = path.stat().st_size
        observed_digest = _sha256_file(path)
    except (OSError, ValueError) as error:
        raise TransformerFitError("transformer_fit_artifact_unreadable") from error
    if observed_size != size or observed_digest != digest:
        raise TransformerFitError("transformer_fit_artifact_hash_mismatch")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _build_report(
    manifest: Mapping[str, Any],
    split_sha256: str,
    commit_sha: str,
    trained_at: datetime,
    configuration: BatchConfiguration,
    probe_attempts: list[dict[str, Any]],
    class_weights: tuple[float, ...],
    optimizer_steps_per_epoch: int,
    history: list[dict[str, Any]],
    selected: Mapping[str, Any],
    stopped_early: bool,
    peak_cuda_bytes: int,
    artifacts: Mapping[str, Any],
    torch: Any,
    software_versions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    software = dict(software_versions or _software_versions())
    return {
        "report_version": REPORT_VERSION,
        "run_id": manifest["run_id"],
        "trained_at_utc": trained_at.isoformat().replace("+00:00", "Z"),
        "source": {
            "split_manifest_sha256": split_sha256,
            "split_version": SPLIT_VERSION,
            "training_implementation_commit_sha": commit_sha,
        },
        "data": {
            "feature_input": "consumer_complaint_narrative_only",
            "train_record_count": manifest["split_counts"]["train"],
            "validation_record_count": manifest["split_counts"]["validation"],
            "test_accessed": False,
            "labels": list(LABELS),
        },
        "model": {
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "maximum_length": 384,
            "label_count": len(LABELS),
            "full_fine_tune": True,
            "safetensors_required": True,
        },
        "optimization": {
            "optimizer": "AdamW",
            "learning_rate": LEARNING_RATE,
            "weight_decay": WEIGHT_DECAY,
            "betas": list(ADAM_BETAS),
            "epsilon": ADAM_EPSILON,
            "scheduler": "linear_decay",
            "warmup_ratio": WARMUP_RATIO,
            "maximum_epochs": MAXIMUM_EPOCHS,
            "gradient_clip_l2": MAX_GRADIENT_NORM,
            "mixed_precision": "fp16",
            "random_seed": 42,
            "per_device_batch_size": configuration.per_device_batch_size,
            "gradient_accumulation_steps": configuration.gradient_accumulation_steps,
            "gradient_checkpointing": configuration.gradient_checkpointing,
            "effective_batch_size": 32,
            "optimizer_steps_per_epoch": optimizer_steps_per_epoch,
            "class_weights": {
                label: float(class_weights[index]) for index, label in enumerate(LABELS)
            },
            "batch_probe_attempts": probe_attempts,
        },
        "selection": {
            "split": "validation",
            "monitored_metric": "macro_f1",
            "minimum_improvement": MINIMUM_MACRO_F1_IMPROVEMENT,
            "patience_completed_epochs": EARLY_STOPPING_PATIENCE,
            "ranking": [
                "highest_validation_macro_f1",
                "highest_validation_worst_class_recall",
                "highest_validation_weighted_f1",
                "earlier_epoch",
            ],
            "completed_epochs": len(history),
            "stopped_early": stopped_early,
            "selected_epoch": selected["epoch"],
        },
        "epochs": history,
        "artifacts": dict(artifacts),
        "runtime": {
            "summed_epoch_compute_seconds": round(
                sum(
                    float(epoch["training"]["elapsed_seconds"])
                    + float(epoch["validation"]["elapsed_seconds"])
                    for epoch in history
                ),
                3,
            ),
            "peak_cuda_bytes": peak_cuda_bytes,
        },
        "software": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "cuda_runtime": torch.version.cuda,
            **software,
        },
        "hardware": {
            "device": torch.cuda.get_device_name(0),
            "compute_capability": list(torch.cuda.get_device_capability(0)),
        },
        "checks": {
            "source_counts_reconcile": True,
            "taxonomy_complete": True,
            "training_uses_train_only": True,
            "selection_uses_validation_only": True,
            "test_accessed": False,
            "losses_finite": True,
            "selected_artifacts_hashed": True,
            "no_rows_persisted": True,
        },
        "claims": {
            "portfolio_promotion_approved": False,
            "test_used_for_training_or_tuning": False,
            "interpretation": "validation_selected_transformer_not_final_test_evidence",
        },
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_token_ids": False,
            "contains_vocabulary": False,
            "artifact_git_tracking_allowed": False,
            "report_git_tracking_allowed": True,
        },
    }


def _read_manifest_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise TransformerFitError("transformer_fit_split_manifest_unreadable") from error


def _software_versions() -> dict[str, str]:
    try:
        return {
            "transformers": version("transformers"),
            "tokenizers": version("tokenizers"),
            "safetensors": version("safetensors"),
            "numpy": version("numpy"),
        }
    except ImportError as error:
        raise TransformerFitError("transformer_fit_dependency_missing") from error


def _report_path(root: Path, run_id: str) -> Path:
    return (
        root / "data" / "evaluations" / "cfpb" / "transformer" / f"{run_id}-{REPORT_VERSION}.json"
    )


def _artifact_directory(root: Path, run_id: str) -> Path:
    return root / "artifacts" / "cfpb" / "transformer" / run_id


def _load_existing_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerFitError("transformer_fit_report_unreadable") from error
    if not isinstance(report, dict):
        raise TransformerFitError("transformer_fit_report_invalid")
    _validate_report(report)
    return report


def _validate_report(report: Mapping[str, Any]) -> None:
    try:
        schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerFitError("transformer_fit_report_schema_unreadable") from error
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise TransformerFitError("transformer_fit_report_invalid", issue_count=len(errors))


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
        raise TransformerFitError("transformer_fit_json_write_failed") from error
    finally:
        temporary.unlink(missing_ok=True)


def _import_fit_torch() -> Any:
    try:
        return _import_torch()
    except TransformerTrainingError as error:
        raise TransformerFitError(error.code, **error.details) from error


def _validate_fit_hardware(torch: Any) -> None:
    try:
        _validate_hardware(torch)
    except TransformerTrainingError as error:
        raise TransformerFitError(error.code, **error.details) from error


def _emit(progress: ProgressReporter | None, event: Mapping[str, Any]) -> None:
    if progress is not None:
        progress(event)
