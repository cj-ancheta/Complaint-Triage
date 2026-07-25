"""Validation-only temperature scaling for the accepted MiniLM candidate."""

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
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
from jsonschema import Draft202012Validator, FormatChecker
from scipy.optimize import minimize_scalar

from complaint_triage.analytical_population import POPULATION_VERSION
from complaint_triage.db import DatabaseSettings
from complaint_triage.live_extraction import read_git_lineage
from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.temporal_split import SPLIT_SCHEMA_PATH, SPLIT_VERSION
from complaint_triage.transformer_dataset import (
    ID_TO_LABEL,
    LABEL_TO_ID,
    LABELS,
    LENGTH_GROUP_POOL_SIZE,
    MAXIMUM_LENGTH,
    RANDOM_SEED,
    TOKENIZE_BATCH_SIZE,
    TransformerDatasetError,
    collate_dynamic,
)
from complaint_triage.transformer_fit import REPORT_SCHEMA_PATH as TRANSFORMER_SCHEMA_PATH
from complaint_triage.transformer_token_profile import (
    TransformerTokenProfileError,
    load_pinned_tokenizer,
)
from complaint_triage.transformer_training import (
    TransformerTrainingError,
    load_pinned_sequence_classifier,
)
from complaint_triage.validation_comparison import REPORT_SCHEMA_PATH as COMPARISON_SCHEMA_PATH

REPORT_VERSION = "transformer-temperature-calibration-1.0.0"
ARTIFACT_VERSION = "temperature-scaling-1.0.0"
TRANSFORMER_REPORT_VERSION = "transformer-minilm-selection-1.0.0"
COMPARISON_REPORT_VERSION = "validation-model-comparison-1.0.0"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-transformer-calibration.schema.json"
FIT_START = date(2024, 9, 1)
FIT_END = date(2024, 10, 1)
EVALUATION_END = date(2024, 11, 1)
EXPECTED_PARTITION_COUNTS = {"calibration_fit": 39_161, "calibration_evaluation": 41_831}
EXPECTED_PARTITION_CLASS_COUNTS = {
    "calibration_fit": {
        "Checking or savings account": 2_347,
        "Credit card": 2_543,
        "Credit reporting or other personal consumer reports": 26_300,
        "Debt collection": 4_101,
        "Debt or credit management": 98,
        "Money transfer, virtual currency, or money service": 782,
        "Mortgage": 1_025,
        "Payday loan, title loan, personal loan, or advance loan": 414,
        "Prepaid card": 184,
        "Student loan": 756,
        "Vehicle loan or lease": 611,
    },
    "calibration_evaluation": {
        "Checking or savings account": 2_614,
        "Credit card": 2_652,
        "Credit reporting or other personal consumer reports": 27_712,
        "Debt collection": 4_683,
        "Debt or credit management": 129,
        "Money transfer, virtual currency, or money service": 902,
        "Mortgage": 1_011,
        "Payday loan, title loan, personal loan, or advance loan": 491,
        "Prepaid card": 268,
        "Student loan": 725,
        "Vehicle loan or lease": 644,
    },
}
ECE_BIN_COUNT = 15
TEMPERATURE_LOWER = 0.05
TEMPERATURE_UPPER = 20.0
LOG_BOUNDARY_TOLERANCE = 1e-6
OPTIMIZER_XATOL = 1e-8
OPTIMIZER_MAXITER = 500
PROBABILITY_SUM_TOLERANCE = 1e-12
BRIER_GUARD_TOLERANCE = 1e-6
RETENTION = "local_only_governed_until_2026-11-19"
FETCH_SIZE = 2_000
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

LineageReader = Callable[[Path], tuple[str, bool]]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class CalibrationInference:
    logits: np.ndarray
    labels: np.ndarray
    partitions: np.ndarray
    top_2_correct: np.ndarray
    elapsed_seconds: float
    peak_cuda_bytes: int


class TransformerCalibrationError(Exception):
    """A controlled calibration failure containing no row-level values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_transformer_calibration_error(error: TransformerCalibrationError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "complaint_ids_logged": False,
            "row_values_in_report": False,
            "row_logits_logged": False,
            "row_probabilities_logged": False,
            "token_ids_logged": False,
        },
    }


def calibrate_transformer(
    transformer_report_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
    lineage_reader: LineageReader = read_git_lineage,
    clock: Clock = lambda: datetime.now(UTC),
    artifact_verifier: Callable[[Path, Mapping[str, Any]], None] | None = None,
    inference_runner: Callable[..., CalibrationInference] | None = None,
    software_reader: Callable[[], Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Fit September temperature scaling and assess it once on October."""

    root = repository_root.resolve()
    transformer, transformer_bytes = _load_report(
        transformer_report_path,
        root / "data" / "evaluations" / "cfpb" / "transformer",
        TRANSFORMER_SCHEMA_PATH,
        TRANSFORMER_REPORT_VERSION,
        "transformer",
    )
    run_id = transformer["run_id"]
    comparison_path = (
        root
        / "data"
        / "evaluations"
        / "cfpb"
        / "model-comparison"
        / f"{run_id}-validation-model-comparison-1.0.0.json"
    )
    comparison, comparison_bytes = _load_report(
        comparison_path,
        comparison_path.parent,
        COMPARISON_SCHEMA_PATH,
        COMPARISON_REPORT_VERSION,
        "comparison",
    )
    split_path = root / "data" / "manifests" / "cfpb" / "splits" / f"{run_id}-split-1.0.0.json"
    split, split_bytes = _load_report(
        split_path, split_path.parent, SPLIT_SCHEMA_PATH, SPLIT_VERSION, "split"
    )
    source_hashes = {
        "transformer_report_sha256": hashlib.sha256(transformer_bytes).hexdigest(),
        "comparison_report_sha256": hashlib.sha256(comparison_bytes).hexdigest(),
        "split_manifest_sha256": hashlib.sha256(split_bytes).hexdigest(),
        "model_artifact_sha256": transformer["artifacts"]["best_model"]["sha256"],
    }
    _validate_source_identity(transformer, comparison, split, source_hashes)
    verify = artifact_verifier or _verify_model_artifact
    verify(root, transformer["artifacts"]["best_model"])

    report_path = _report_path(root, run_id)
    if report_path.exists():
        existing = _load_existing_report(report_path)
        if any(existing["source"][key] != value for key, value in source_hashes.items()):
            raise TransformerCalibrationError("transformer_calibration_report_identity_conflict")
        _verify_calibrator_artifact(root, existing["artifact"])
        return existing

    commit_sha, clean = lineage_reader(root)
    if not SHA40_PATTERN.fullmatch(commit_sha) or not clean:
        raise TransformerCalibrationError("transformer_calibration_requires_clean_commit")
    calibrated_at = clock()
    if calibrated_at.tzinfo is None or calibrated_at.utcoffset() != UTC.utcoffset(calibrated_at):
        raise TransformerCalibrationError("transformer_calibration_clock_invalid")

    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")
    inference = (inference_runner or run_validation_inference)(
        root=root,
        transformer_report=transformer,
        split_manifest=split,
        settings=database_settings,
    )
    _validate_inference(inference, transformer, split)
    fit_mask = inference.partitions == "calibration_fit"
    evaluation_mask = inference.partitions == "calibration_evaluation"
    fit_logits, fit_labels = inference.logits[fit_mask], inference.labels[fit_mask]
    eval_logits, eval_labels = inference.logits[evaluation_mask], inference.labels[evaluation_mask]

    optimization_started = time.perf_counter()
    fit_result = fit_temperature(fit_logits, fit_labels)
    optimization_seconds = round(time.perf_counter() - optimization_started, 6)
    temperature = fit_result["temperature"]
    fit_before = calibration_metrics(fit_logits, fit_labels, temperature=1.0)
    fit_after = calibration_metrics(fit_logits, fit_labels, temperature=temperature)
    eval_before = calibration_metrics(eval_logits, eval_labels, temperature=1.0)
    eval_after = calibration_metrics(eval_logits, eval_labels, temperature=temperature)
    invariance = _invariance_checks(inference.logits, temperature)
    numerical = _probability_checks(inference.logits, temperature)
    eligibility_checks = {
        "optimizer_converged_away_from_bounds": True,
        "probabilities_valid": numerical["valid"],
        "argmax_unchanged": invariance["argmax_unchanged"],
        "top_2_membership_unchanged": invariance["top_2_membership_unchanged"],
        "partition_counts_reconcile": True,
        "evaluation_nll_improved": eval_after["negative_log_likelihood"]
        < eval_before["negative_log_likelihood"],
        "evaluation_brier_guard_passed": eval_after["multiclass_brier_loss"]
        <= eval_before["multiclass_brier_loss"] + BRIER_GUARD_TOLERANCE,
    }
    artifact_path = _artifact_path(root, run_id)
    artifact_value = {
        "artifact_version": ARTIFACT_VERSION,
        "temperature": temperature,
        "labels": list(LABELS),
        **source_hashes,
        "calibration_implementation_commit_sha": commit_sha,
        "method": "scalar_temperature_scaling",
        "fit_partition": "validation_2024_09",
    }
    _atomic_json(artifact_path, artifact_value)
    artifact = _artifact_metadata(artifact_path, root)

    report = _build_calibration_report(
        run_id=run_id,
        calibrated_at=calibrated_at,
        source_hashes=source_hashes,
        commit_sha=commit_sha,
        inference=inference,
        temperature=temperature,
        fit_result=fit_result,
        fit_before=fit_before,
        fit_after=fit_after,
        eval_before=eval_before,
        eval_after=eval_after,
        eligibility_checks=eligibility_checks,
        artifact=artifact,
        optimization_seconds=optimization_seconds,
        numerical=numerical,
        invariance=invariance,
        software=(software_reader or _software_versions)(),
    )
    _validate_report(report)
    _atomic_json(report_path, report)
    return report


def _build_calibration_report(
    *,
    run_id: str,
    calibrated_at: datetime,
    source_hashes: Mapping[str, str],
    commit_sha: str,
    inference: CalibrationInference,
    temperature: float,
    fit_result: Mapping[str, float | int],
    fit_before: Mapping[str, Any],
    fit_after: Mapping[str, Any],
    eval_before: Mapping[str, Any],
    eval_after: Mapping[str, Any],
    eligibility_checks: Mapping[str, bool],
    artifact: Mapping[str, Any],
    optimization_seconds: float,
    numerical: Mapping[str, bool],
    invariance: Mapping[str, bool],
    software: Mapping[str, str],
) -> dict[str, Any]:
    """Build privacy-bounded calibration evidence from validated aggregates."""
    eligible = all(eligibility_checks.values())
    evaluation_per_class = per_class_calibration(
        inference.logits[inference.partitions == "calibration_evaluation"],
        inference.labels[inference.partitions == "calibration_evaluation"],
        temperature,
    )
    return {
        "report_version": REPORT_VERSION,
        "run_id": run_id,
        "calibrated_at_utc": calibrated_at.isoformat().replace("+00:00", "Z"),
        "source": {**source_hashes, "calibration_implementation_commit_sha": commit_sha},
        "data": {
            "evaluation_split": "validation",
            "labels": list(LABELS),
            "partitions": _partition_evidence(inference.labels, inference.partitions),
            "test_accessed": False,
        },
        "method": {
            "kind": "scalar_temperature_scaling",
            "objective": "mean_categorical_negative_log_likelihood",
            "parameterization": "bounded_log_temperature",
            "temperature_lower_bound": TEMPERATURE_LOWER,
            "temperature_upper_bound": TEMPERATURE_UPPER,
            "xatol_log_temperature": OPTIMIZER_XATOL,
            "maximum_iterations": OPTIMIZER_MAXITER,
            "temperature": temperature,
            "optimizer_iterations": fit_result["iterations"],
            "optimizer_function_calls": fit_result["function_calls"],
            "optimizer_converged": True,
        },
        "results": {
            "calibration_fit": {"before": fit_before, "after": fit_after},
            "calibration_evaluation": {
                "before": eval_before,
                "after": eval_after,
                "per_class": evaluation_per_class,
            },
        },
        "eligibility": {
            "checks": eligibility_checks,
            "calibrator_eligible_for_ct306": eligible,
            "proposal_for_ct306": (
                "calibrated_transformer_probabilities"
                if eligible
                else "uncalibrated_transformer_probabilities"
            ),
            "final_operational_model_selected": False,
        },
        "artifact": artifact,
        "runtime": {
            "gpu_inference_seconds": inference.elapsed_seconds,
            "peak_cuda_bytes": inference.peak_cuda_bytes,
            "cpu_optimization_seconds": optimization_seconds,
        },
        "software": dict(software),
        "checks": {
            "source_identity_reconciled": True,
            "model_artifact_verified_before_load": True,
            "accepted_predictions_reproduced": True,
            "partition_counts_reconcile": True,
            "class_counts_reconcile": True,
            "probabilities_finite_and_normalized": numerical["valid"],
            "predictions_unchanged": invariance["argmax_unchanged"],
            "top_2_unchanged": invariance["top_2_membership_unchanged"],
            "artifact_hashed": True,
            "test_accessed": False,
        },
        "limitations": [
            "base_model_selected_using_complete_validation_period",
            "september_metrics_are_in_sample_calibration_fit_diagnostics",
            "october_metrics_are_validation_tuning_evidence_not_final_test_evidence",
            "temperature_scaling_cannot_fix_class_specific_or_input_dependent_miscalibration",
            "ece_estimates_depend_on_declared_binning",
            "rare_class_calibration_metrics_have_higher_variance",
            "no_abstention_threshold_selected_in_ct305",
        ],
        "claims": {
            "portfolio_promotion_approved": False,
            "test_used_for_calibration": False,
            "operational_threshold_selected": False,
            "final_operational_model_selected": False,
            "interpretation": "validation_only_temperature_calibration",
        },
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_row_logits": False,
            "contains_row_probabilities": False,
            "contains_token_ids": False,
            "artifact_git_tracking_allowed": False,
            "report_git_tracking_allowed": True,
        },
    }


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> dict[str, float | int]:
    _validate_arrays(logits, labels)
    lower, upper = math.log(TEMPERATURE_LOWER), math.log(TEMPERATURE_UPPER)

    def objective(log_temperature: float) -> float:
        return categorical_nll(logits, labels, temperature=math.exp(log_temperature))

    result = minimize_scalar(
        objective,
        bounds=(lower, upper),
        method="bounded",
        options={"xatol": OPTIMIZER_XATOL, "maxiter": OPTIMIZER_MAXITER},
    )
    if (
        not result.success
        or not math.isfinite(float(result.x))
        or not math.isfinite(float(result.fun))
    ):
        raise TransformerCalibrationError("transformer_calibration_optimizer_failed")
    if min(float(result.x) - lower, upper - float(result.x)) <= LOG_BOUNDARY_TOLERANCE:
        raise TransformerCalibrationError("transformer_calibration_temperature_at_bound")
    return {
        "temperature": math.exp(float(result.x)),
        "negative_log_likelihood": float(result.fun),
        "iterations": int(result.nit),
        "function_calls": int(result.nfev),
    }


def probabilities_from_logits(logits: np.ndarray, *, temperature: float) -> np.ndarray:
    if not math.isfinite(temperature) or temperature <= 0:
        raise TransformerCalibrationError("transformer_calibration_temperature_invalid")
    values = np.asarray(logits, dtype=np.float64) / temperature
    if values.ndim != 2 or values.shape[1] != len(LABELS) or not np.isfinite(values).all():
        raise TransformerCalibrationError("transformer_calibration_logits_invalid")
    values -= values.max(axis=1, keepdims=True)
    exponentiated = np.exp(values)
    return exponentiated / exponentiated.sum(axis=1, keepdims=True)


def categorical_nll(logits: np.ndarray, labels: np.ndarray, *, temperature: float) -> float:
    _validate_arrays(logits, labels)
    if not math.isfinite(temperature) or temperature <= 0:
        raise TransformerCalibrationError("transformer_calibration_temperature_invalid")
    scaled = np.asarray(logits, dtype=np.float64) / temperature
    maximum = scaled.max(axis=1)
    log_normalizer = maximum + np.log(np.exp(scaled - maximum[:, None]).sum(axis=1))
    return float((log_normalizer - scaled[np.arange(labels.size), labels]).mean())


def calibration_metrics(
    logits: np.ndarray, labels: np.ndarray, *, temperature: float
) -> dict[str, Any]:
    _validate_arrays(logits, labels)
    probabilities = probabilities_from_logits(logits, temperature=temperature)
    predictions = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    correct = predictions == labels
    width_bins = equal_width_reliability(confidence, correct, bin_count=ECE_BIN_COUNT)
    accuracy = float(correct.mean())
    mean_confidence = float(confidence.mean())
    one_hot = np.eye(len(LABELS), dtype=np.float64)[labels]
    return {
        "record_count": int(labels.size),
        "negative_log_likelihood": categorical_nll(logits, labels, temperature=temperature),
        "multiclass_brier_loss": float(np.square(probabilities - one_hot).sum(axis=1).mean()),
        "accuracy": accuracy,
        "mean_top_label_confidence": mean_confidence,
        "signed_confidence_minus_accuracy": mean_confidence - accuracy,
        "top_label_ece_equal_width_15": _ece_from_bins(width_bins, labels.size),
        "top_label_ece_equal_mass_15": equal_mass_ece(confidence, correct, bin_count=ECE_BIN_COUNT),
        "equal_width_reliability_bins": width_bins,
    }


def equal_width_reliability(
    confidence: np.ndarray, correct: np.ndarray, *, bin_count: int
) -> list[dict[str, Any]]:
    confidence = np.asarray(confidence, dtype=np.float64)
    correct = np.asarray(correct, dtype=bool)
    if confidence.ndim != 1 or correct.shape != confidence.shape or not confidence.size:
        raise TransformerCalibrationError("transformer_calibration_metric_input_invalid")
    if not np.isfinite(confidence).all() or np.any((confidence < 0) | (confidence > 1)):
        raise TransformerCalibrationError("transformer_calibration_metric_input_invalid")
    edges = np.linspace(0.0, 1.0, bin_count + 1)
    assignments = np.minimum(np.floor(confidence * bin_count).astype(int), bin_count - 1)
    bins = []
    for index in range(bin_count):
        mask = assignments == index
        count = int(mask.sum())
        accuracy = float(correct[mask].mean()) if count else None
        mean_confidence = float(confidence[mask].mean()) if count else None
        bins.append(
            {
                "bin_index": index,
                "lower_inclusive": float(edges[index]),
                "upper_inclusive": float(edges[index + 1]) if index == bin_count - 1 else None,
                "upper_exclusive": float(edges[index + 1]) if index < bin_count - 1 else None,
                "record_count": count,
                "correct_count": int(correct[mask].sum()),
                "mean_confidence": mean_confidence,
                "accuracy": accuracy,
                "absolute_gap": (abs(mean_confidence - accuracy) if count else None),
            }
        )
    return bins


def equal_mass_ece(confidence: np.ndarray, correct: np.ndarray, *, bin_count: int) -> float:
    order = np.argsort(np.asarray(confidence), kind="stable")
    groups = np.array_split(order, bin_count)
    total = len(order)
    return float(
        sum(
            len(group)
            / total
            * abs(
                float(np.asarray(confidence)[group].mean())
                - float(np.asarray(correct)[group].mean())
            )
            for group in groups
            if len(group)
        )
    )


def per_class_calibration(
    logits: np.ndarray, labels: np.ndarray, temperature: float
) -> list[dict[str, Any]]:
    before = probabilities_from_logits(logits, temperature=1.0)
    after = probabilities_from_logits(logits, temperature=temperature)
    result = []
    for index, label in enumerate(LABELS):
        actual = labels == index
        result.append(
            {
                "label": label,
                "support": int(actual.sum()),
                "prevalence": float(actual.mean()),
                "before": _class_probability_metrics(before[:, index], actual),
                "after": _class_probability_metrics(after[:, index], actual),
            }
        )
    return result


def _class_probability_metrics(probabilities: np.ndarray, actual: np.ndarray) -> dict[str, float]:
    mean_probability = float(probabilities.mean())
    prevalence = float(actual.mean())
    return {
        "mean_probability": mean_probability,
        "absolute_prevalence_gap": abs(mean_probability - prevalence),
        "one_vs_rest_brier_loss": float(np.square(probabilities - actual).mean()),
    }


def run_validation_inference(
    *,
    root: Path,
    transformer_report: Mapping[str, Any],
    split_manifest: Mapping[str, Any],
    settings: DatabaseSettings,
) -> CalibrationInference:
    """Run the canonical validation batches once and retain logits only in memory."""

    try:
        import torch
        from safetensors.torch import load_file
    except ImportError as error:
        raise TransformerCalibrationError("transformer_calibration_dependency_missing") from error
    if (
        torch.__version__ != "2.13.0+cu130"
        or not torch.cuda.is_available()
        or torch.version.cuda != "13.0"
        or torch.cuda.get_device_capability(0) != (12, 0)
    ):
        raise TransformerCalibrationError("transformer_calibration_cuda_boundary_mismatch")
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    torch.manual_seed(RANDOM_SEED)
    torch.cuda.manual_seed_all(RANDOM_SEED)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.use_deterministic_algorithms(True)
    try:
        tokenizer = load_pinned_tokenizer(root).tokenizer
        model = load_pinned_sequence_classifier(root).to("cuda")
        state = load_file(
            root / transformer_report["artifacts"]["best_model"]["relative_path"], device="cuda"
        )
        model.load_state_dict(state, strict=True)
        del state
        model.eval()
    except (
        OSError,
        RuntimeError,
        ValueError,
        TransformerTokenProfileError,
        TransformerTrainingError,
    ) as error:
        raise TransformerCalibrationError("transformer_calibration_model_load_failed") from error
    batch_size = int(transformer_report["optimization"]["per_device_batch_size"])
    batches = _stream_partitioned_batches(
        split_manifest, settings, tokenizer, batch_size=batch_size
    )
    logits_parts: list[np.ndarray] = []
    label_parts: list[np.ndarray] = []
    partition_parts: list[np.ndarray] = []
    top_2_parts: list[np.ndarray] = []
    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    try:
        with torch.inference_mode():
            for batch, partitions in batches:
                labels = batch["labels"].to("cuda", non_blocking=True)
                inputs = {
                    key: value.to("cuda", non_blocking=True)
                    for key, value in batch.items()
                    if key != "labels"
                }
                with torch.amp.autocast("cuda", dtype=torch.float16):
                    logits = model(**inputs).logits
                if not torch.isfinite(logits).all():
                    raise TransformerCalibrationError("transformer_calibration_logits_nonfinite")
                logits_parts.append(logits.float().cpu().numpy().astype(np.float64))
                label_parts.append(labels.cpu().numpy().astype(np.int64))
                partition_parts.append(np.asarray(partitions, dtype="U24"))
                top_2_parts.append(
                    (logits.topk(k=2, dim=1).indices == labels.unsqueeze(1))
                    .any(dim=1)
                    .cpu()
                    .numpy()
                    .astype(bool)
                )
        return CalibrationInference(
            logits=np.concatenate(logits_parts),
            labels=np.concatenate(label_parts),
            partitions=np.concatenate(partition_parts),
            top_2_correct=np.concatenate(top_2_parts),
            elapsed_seconds=round(time.perf_counter() - started, 3),
            peak_cuda_bytes=int(torch.cuda.max_memory_allocated()),
        )
    except TransformerCalibrationError:
        raise
    except TransformerDatasetError as error:
        raise TransformerCalibrationError(error.code, **error.details) from error
    except (OSError, RuntimeError, ValueError) as error:
        raise TransformerCalibrationError("transformer_calibration_inference_failed") from error
    finally:
        del model
        torch.cuda.empty_cache()


def iter_validation_rows(
    manifest: Mapping[str, Any], settings: DatabaseSettings
) -> Iterable[tuple[str, str, date]]:
    query = """
        SELECT s.narrative, p.target_product, s.date_received
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
          AND o.split_assignment = 'validation'
        ORDER BY o.raw_batch_id, o.source_row_ordinal
    """
    parameters = (manifest["run_id"], SPLIT_VERSION, POPULATION_VERSION)
    try:
        with psycopg.connect(settings.psycopg_conninfo()) as connection:
            with connection.cursor(name=f"transformer_calibration_{uuid.uuid4().hex}") as cursor:
                cursor.execute(query, parameters)
                while rows := cursor.fetchmany(FETCH_SIZE):
                    yield from rows
    except psycopg.Error as error:
        raise TransformerCalibrationError("transformer_calibration_database_failed") from error


def _stream_partitioned_batches(
    manifest: Mapping[str, Any], settings: DatabaseSettings, tokenizer: Any, *, batch_size: int
) -> Iterator[tuple[Mapping[str, Any], list[str]]]:
    features = _tokenize_partitioned_rows(iter_validation_rows(manifest, settings), tokenizer)
    generator = random.Random(RANDOM_SEED)
    pool: list[tuple[dict[str, Any], str]] = []

    def emit_pool() -> Iterator[tuple[Mapping[str, Any], list[str]]]:
        pool.sort(key=lambda item: len(item[0]["input_ids"]))
        groups = [pool[index : index + batch_size] for index in range(0, len(pool), batch_size)]
        generator.shuffle(groups)
        for group in groups:
            yield (
                collate_dynamic([item[0] for item in group], tokenizer, return_tensors="pt"),
                [item[1] for item in group],
            )
        pool.clear()

    for item in features:
        pool.append(item)
        if len(pool) == LENGTH_GROUP_POOL_SIZE:
            yield from emit_pool()
    yield from emit_pool()


def _tokenize_partitioned_rows(
    rows: Iterable[tuple[str, str, date]], tokenizer: Any
) -> Iterator[tuple[dict[str, Any], str]]:
    texts: list[str] = []
    labels: list[str] = []
    partitions: list[str] = []

    def consume() -> Iterator[tuple[dict[str, Any], str]]:
        if not texts:
            return
        try:
            encoded = tokenizer(
                texts,
                add_special_tokens=True,
                padding=False,
                truncation=True,
                max_length=MAXIMUM_LENGTH,
                return_attention_mask=True,
                return_token_type_ids=True,
                verbose=False,
            )
        except (TypeError, ValueError, RuntimeError) as error:
            raise TransformerCalibrationError(
                "transformer_calibration_tokenization_failed"
            ) from error
        if any(
            key not in encoded or len(encoded[key]) != len(texts)
            for key in ("input_ids", "attention_mask")
        ):
            raise TransformerCalibrationError("transformer_calibration_tokenization_invalid")
        if "token_type_ids" in encoded and len(encoded["token_type_ids"]) != len(texts):
            raise TransformerCalibrationError("transformer_calibration_tokenization_invalid")
        for index, label in enumerate(labels):
            feature = {
                "input_ids": list(encoded["input_ids"][index]),
                "attention_mask": list(encoded["attention_mask"][index]),
                "labels": LABEL_TO_ID[label],
            }
            if "token_type_ids" in encoded:
                feature["token_type_ids"] = list(encoded["token_type_ids"][index])
            yield feature, partitions[index]
        texts.clear()
        labels.clear()
        partitions.clear()

    for narrative, label, received in rows:
        if not isinstance(narrative, str) or not narrative.strip() or label not in LABEL_TO_ID:
            raise TransformerCalibrationError("transformer_calibration_source_row_invalid")
        partition = _partition_for_date(received)
        texts.append(narrative)
        labels.append(label)
        partitions.append(partition)
        if len(texts) == TOKENIZE_BATCH_SIZE:
            yield from consume()
    yield from consume()


def _partition_for_date(received: date) -> str:
    if not isinstance(received, date) or isinstance(received, datetime):
        raise TransformerCalibrationError("transformer_calibration_date_invalid")
    if FIT_START <= received < FIT_END:
        return "calibration_fit"
    if FIT_END <= received < EVALUATION_END:
        return "calibration_evaluation"
    raise TransformerCalibrationError("transformer_calibration_date_outside_boundary")


def _validate_inference(
    inference: CalibrationInference,
    transformer: Mapping[str, Any],
    split: Mapping[str, Any],
) -> None:
    _validate_arrays(inference.logits, inference.labels)
    if inference.partitions.shape != inference.labels.shape:
        raise TransformerCalibrationError("transformer_calibration_partition_shape_invalid")
    if inference.top_2_correct.shape != inference.labels.shape:
        raise TransformerCalibrationError("transformer_calibration_top2_shape_invalid")
    counts = Counter(inference.partitions.tolist())
    if dict(counts) != EXPECTED_PARTITION_COUNTS:
        raise TransformerCalibrationError("transformer_calibration_partition_counts_mismatch")
    combined_counts = Counter(ID_TO_LABEL[int(value)] for value in inference.labels)
    if dict(combined_counts) != split["class_counts_by_split"]["validation"]:
        raise TransformerCalibrationError("transformer_calibration_class_counts_mismatch")
    for partition, expected in EXPECTED_PARTITION_CLASS_COUNTS.items():
        observed = Counter(
            ID_TO_LABEL[int(value)] for value in inference.labels[inference.partitions == partition]
        )
        if dict(observed) != expected:
            raise TransformerCalibrationError(
                "transformer_calibration_partition_class_counts_mismatch",
                partition=partition,
            )
    selected = next(
        epoch
        for epoch in transformer["epochs"]
        if epoch["epoch"] == transformer["selection"]["selected_epoch"]
    )
    predictions = inference.logits.argmax(axis=1)
    matrix = np.zeros((len(LABELS), len(LABELS)), dtype=np.int64)
    np.add.at(matrix, (inference.labels, predictions), 1)
    if matrix.tolist() != selected["validation"]["metrics"]["confusion_matrix"]["rows"]:
        raise TransformerCalibrationError("transformer_calibration_predictions_do_not_reproduce")
    top2_count = int(inference.top_2_correct.sum())
    expected_top2 = selected["validation"]["metrics"]["top_2_accuracy"]
    if not math.isclose(top2_count / inference.labels.size, expected_top2, abs_tol=1e-15):
        raise TransformerCalibrationError("transformer_calibration_top2_does_not_reproduce")


def _validate_arrays(logits: np.ndarray, labels: np.ndarray) -> None:
    logits = np.asarray(logits)
    labels = np.asarray(labels)
    if (
        logits.ndim != 2
        or logits.shape[1] != len(LABELS)
        or labels.ndim != 1
        or logits.shape[0] != labels.size
        or not labels.size
        or not np.issubdtype(labels.dtype, np.integer)
        or np.any((labels < 0) | (labels >= len(LABELS)))
        or not np.isfinite(logits).all()
    ):
        raise TransformerCalibrationError("transformer_calibration_arrays_invalid")


def _invariance_checks(logits: np.ndarray, temperature: float) -> dict[str, bool]:
    before = probabilities_from_logits(logits, temperature=1.0)
    after = probabilities_from_logits(logits, temperature=temperature)
    return {
        "argmax_unchanged": bool(np.array_equal(before.argmax(axis=1), after.argmax(axis=1))),
        "top_2_membership_unchanged": bool(
            np.array_equal(
                np.sort(np.argpartition(before, -2, axis=1)[:, -2:], axis=1),
                np.sort(np.argpartition(after, -2, axis=1)[:, -2:], axis=1),
            )
        ),
    }


def _probability_checks(logits: np.ndarray, temperature: float) -> dict[str, Any]:
    probabilities = probabilities_from_logits(logits, temperature=temperature)
    maximum_sum_error = float(np.abs(probabilities.sum(axis=1) - 1.0).max())
    return {
        "valid": bool(
            np.isfinite(probabilities).all()
            and np.all((probabilities >= 0) & (probabilities <= 1))
            and maximum_sum_error <= PROBABILITY_SUM_TOLERANCE
        ),
        "maximum_sum_error": maximum_sum_error,
    }


def _ece_from_bins(bins: Sequence[Mapping[str, Any]], total: int) -> float:
    return float(sum(item["record_count"] / total * (item["absolute_gap"] or 0.0) for item in bins))


def _partition_evidence(labels: np.ndarray, partitions: np.ndarray) -> list[dict[str, Any]]:
    results = []
    for partition, start, end in (
        ("calibration_fit", FIT_START, FIT_END),
        ("calibration_evaluation", FIT_END, EVALUATION_END),
    ):
        selected = labels[partitions == partition]
        counts = Counter(ID_TO_LABEL[int(value)] for value in selected)
        results.append(
            {
                "partition": partition,
                "start_inclusive": start.isoformat(),
                "end_exclusive": end.isoformat(),
                "record_count": int(selected.size),
                "class_counts": {label: counts[label] for label in LABELS},
            }
        )
    return results


def _load_report(
    path: Path,
    expected_parent: Path,
    schema_path: Path,
    expected_version: str,
    source_name: str,
) -> tuple[dict[str, Any], bytes]:
    resolved = path.resolve()
    if resolved.parent != expected_parent.resolve():
        raise TransformerCalibrationError(f"unsafe_transformer_calibration_{source_name}_path")
    try:
        encoded = resolved.read_bytes()
        report = json.loads(encoded)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerCalibrationError(
            f"transformer_calibration_{source_name}_unreadable"
        ) from error
    if not isinstance(report, dict):
        raise TransformerCalibrationError(f"transformer_calibration_{source_name}_schema_invalid")
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    observed_version = report.get(
        "report_version", report.get("split_manifest_version", report.get("split_version"))
    )
    if errors or observed_version != expected_version:
        raise TransformerCalibrationError(
            f"transformer_calibration_{source_name}_schema_invalid", issue_count=len(errors)
        )
    return report, encoded


def _validate_source_identity(
    transformer: Mapping[str, Any],
    comparison: Mapping[str, Any],
    split: Mapping[str, Any],
    hashes: Mapping[str, str],
) -> None:
    run_id = transformer["run_id"]
    if comparison["run_id"] != run_id or split["run_id"] != run_id:
        raise TransformerCalibrationError("transformer_calibration_run_identity_mismatch")
    split_hash = hashes["split_manifest_sha256"]
    if (
        transformer["source"]["split_manifest_sha256"] != split_hash
        or comparison["source"]["split_manifest_sha256"] != split_hash
        or comparison["source"]["transformer_report_sha256"] != hashes["transformer_report_sha256"]
    ):
        raise TransformerCalibrationError("transformer_calibration_source_identity_mismatch")
    if (
        comparison["utility_proposal"]["candidate_for_calibration"] != "transformer_minilm"
        or transformer["data"]["test_accessed"]
        or comparison["data"]["test_accessed"]
    ):
        raise TransformerCalibrationError("transformer_calibration_source_boundary_invalid")


def _verify_model_artifact(root: Path, metadata: Mapping[str, Any]) -> None:
    _verify_artifact(root, metadata, "artifacts/cfpb/transformer/")


def _verify_calibrator_artifact(root: Path, metadata: Mapping[str, Any]) -> None:
    _verify_artifact(root, metadata, "artifacts/cfpb/transformer/")


def _verify_artifact(root: Path, metadata: Mapping[str, Any], prefix: str) -> None:
    relative = metadata.get("relative_path")
    digest = metadata.get("sha256")
    byte_count = metadata.get("byte_count")
    if (
        not isinstance(relative, str)
        or not relative.startswith(prefix)
        or not isinstance(digest, str)
        or not SHA256_PATTERN.fullmatch(digest)
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 1
    ):
        raise TransformerCalibrationError("transformer_calibration_artifact_metadata_invalid")
    path = (root / relative).resolve()
    try:
        path.relative_to((root / "artifacts" / "cfpb" / "transformer").resolve())
        observed_size = path.stat().st_size
        observed_hash = _file_sha256(path)
    except (OSError, ValueError) as error:
        raise TransformerCalibrationError("transformer_calibration_artifact_unreadable") from error
    if observed_size != byte_count or observed_hash != digest:
        raise TransformerCalibrationError("transformer_calibration_artifact_hash_mismatch")


def _artifact_metadata(path: Path, root: Path) -> dict[str, Any]:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
        byte_count = path.stat().st_size
        digest = _file_sha256(path)
    except (OSError, ValueError) as error:
        raise TransformerCalibrationError(
            "transformer_calibration_artifact_metadata_failed"
        ) from error
    if not relative.startswith("artifacts/cfpb/transformer/"):
        raise TransformerCalibrationError("transformer_calibration_artifact_path_unsafe")
    return {
        "artifact_version": ARTIFACT_VERSION,
        "relative_path": relative,
        "sha256": digest,
        "byte_count": byte_count,
        "retention": RETENTION,
    }


def _load_existing_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TransformerCalibrationError("transformer_calibration_report_unreadable") from error
    if not isinstance(report, dict):
        raise TransformerCalibrationError("transformer_calibration_report_schema_invalid")
    _validate_report(report)
    return report


def _validate_report(report: Mapping[str, Any]) -> None:
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise TransformerCalibrationError(
            "transformer_calibration_report_schema_invalid", issue_count=len(errors)
        )


def _software_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": version("numpy"),
        "scipy": version("scipy"),
        "torch": version("torch"),
        "transformers": version("transformers"),
        "safetensors": version("safetensors"),
    }


def _report_path(root: Path, run_id: str) -> Path:
    return (
        root / "data" / "evaluations" / "cfpb" / "calibration" / f"{run_id}-{REPORT_VERSION}.json"
    )


def _artifact_path(root: Path, run_id: str) -> Path:
    return (
        root
        / "artifacts"
        / "cfpb"
        / "transformer"
        / run_id
        / "calibration"
        / f"{ARTIFACT_VERSION}.json"
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


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
    finally:
        temporary.unlink(missing_ok=True)
