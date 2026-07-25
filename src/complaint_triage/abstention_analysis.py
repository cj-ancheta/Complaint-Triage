"""Governed Phase 4 validation-only abstention threshold analysis."""

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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.analytical_population import POPULATION_VERSION
from complaint_triage.db import DatabaseSettings
from complaint_triage.live_extraction import read_git_lineage
from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.temporal_split import SPLIT_SCHEMA_PATH, SPLIT_VERSION
from complaint_triage.transformer_calibration import (
    EXPECTED_PARTITION_CLASS_COUNTS,
    probabilities_from_logits,
)
from complaint_triage.transformer_dataset import (
    LABELS,
    LENGTH_GROUP_POOL_SIZE,
    RANDOM_SEED,
    TransformerDatasetError,
    collate_dynamic,
    length_grouped_batches,
    tokenize_rows,
)
from complaint_triage.transformer_token_profile import (
    TransformerTokenProfileError,
    load_pinned_tokenizer,
)
from complaint_triage.transformer_training import (
    TransformerTrainingError,
    load_pinned_sequence_classifier,
)

REPORT_VERSION = "abstention-threshold-analysis-1.0.0"
MODEL_SELECTION_REPORT_VERSION = "operational-model-selection-1.0.0"
CALIBRATION_REPORT_VERSION = "transformer-temperature-calibration-1.0.0"
TRANSFORMER_REPORT_VERSION = "transformer-minilm-selection-1.0.0"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-abstention-analysis.schema.json"
REFERENCE_THRESHOLD = 0.0
CANDIDATE_THRESHOLDS = tuple(round(value / 100, 2) for value in range(50, 100, 5))
ALL_THRESHOLDS = (REFERENCE_THRESHOLD, *CANDIDATE_THRESHOLDS)
EXPECTED_RECORD_COUNT = 41_831
EVALUATION_START = "2024-10-01"
EVALUATION_END = "2024-11-01"
MINIMUM_SELECTIVE_ACCURACY = 0.93
MINIMUM_COVERAGE = 0.60
MAXIMUM_FALSE_SUGGESTION_RATE = 0.05
MINIMUM_ACTUAL_CLASS_COVERAGE = 0.10
MINIMUM_PREDICTED_CLASS_SUGGESTIONS = 20
MINIMUM_PREDICTED_CLASS_PRECISION = 0.50
WILSON_Z_95 = 1.959963984540054
REPRODUCTION_ABSOLUTE_TOLERANCE = 1e-5
FETCH_SIZE = 2_000
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

LineageReader = Callable[[Path], tuple[str, bool]]
Clock = Callable[[], datetime]
ArtifactVerifier = Callable[[Path, Mapping[str, Any], str], None]
CalibratorReader = Callable[[Path, Mapping[str, Any], Mapping[str, Any]], float]
ReproductionValidator = Callable[[np.ndarray, np.ndarray, Mapping[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True)
class AbstentionInference:
    """In-memory October logits and labels plus aggregate runtime evidence."""

    logits: np.ndarray
    labels: np.ndarray
    elapsed_seconds: float
    peak_cuda_bytes: int


class AbstentionAnalysisError(Exception):
    """A controlled threshold-analysis failure containing no row values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_abstention_analysis_error(error: AbstentionAnalysisError) -> dict[str, Any]:
    """Return a privacy-safe command error."""

    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "complaint_ids_logged": False,
            "row_logits_logged": False,
            "row_probabilities_logged": False,
            "row_predictions_logged": False,
            "row_threshold_outcomes_logged": False,
            "token_ids_logged": False,
        },
    }


def analyze_abstention_thresholds(
    model_selection_report_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
    lineage_reader: LineageReader = read_git_lineage,
    clock: Clock = lambda: datetime.now(UTC),
    artifact_verifier: ArtifactVerifier | None = None,
    calibrator_reader: CalibratorReader | None = None,
    inference_runner: Callable[..., AbstentionInference] | None = None,
    reproduction_validator: ReproductionValidator | None = None,
    software_reader: Callable[[], Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Evaluate the accepted fixed grid on October validation evidence only."""

    root = repository_root.resolve()
    model_selection, model_selection_bytes = _load_report(
        model_selection_report_path,
        root / "data/evaluations/cfpb/model-selection",
        root / "contracts/cfpb-model-selection.schema.json",
        MODEL_SELECTION_REPORT_VERSION,
        "model_selection",
    )
    run_id = model_selection["run_id"]
    paths = _source_paths(root, run_id)
    calibration, calibration_bytes = _load_report(
        paths["calibration"],
        paths["calibration"].parent,
        root / "contracts/cfpb-transformer-calibration.schema.json",
        CALIBRATION_REPORT_VERSION,
        "calibration",
    )
    transformer, transformer_bytes = _load_report(
        paths["transformer"],
        paths["transformer"].parent,
        root / "contracts/cfpb-transformer-training.schema.json",
        TRANSFORMER_REPORT_VERSION,
        "transformer",
    )
    split, split_bytes = _load_report(
        paths["split"],
        paths["split"].parent,
        root / SPLIT_SCHEMA_PATH.relative_to(PROJECT_ROOT),
        SPLIT_VERSION,
        "split",
    )
    source_hashes = {
        "model_selection_report_sha256": hashlib.sha256(model_selection_bytes).hexdigest(),
        "calibration_report_sha256": hashlib.sha256(calibration_bytes).hexdigest(),
        "transformer_report_sha256": hashlib.sha256(transformer_bytes).hexdigest(),
        "split_manifest_sha256": hashlib.sha256(split_bytes).hexdigest(),
        "model_artifact_sha256": transformer["artifacts"]["best_model"]["sha256"],
        "calibrator_artifact_sha256": calibration["artifact"]["sha256"],
    }
    _validate_source_identity(model_selection, calibration, transformer, split, source_hashes)
    verify = artifact_verifier or _verify_artifact
    verify(root, transformer["artifacts"]["best_model"], "artifacts/cfpb/transformer/")
    verify(root, calibration["artifact"], "artifacts/cfpb/transformer/")
    temperature = (calibrator_reader or _read_calibrator)(
        root, calibration["artifact"], calibration
    )

    report_path = _report_path(root, run_id)
    if report_path.exists():
        existing = _load_existing_report(report_path, root)
        if any(existing["source"].get(key) != value for key, value in source_hashes.items()):
            raise AbstentionAnalysisError("abstention_report_identity_conflict")
        return existing

    commit_sha, clean = lineage_reader(root)
    if not SHA40_PATTERN.fullmatch(commit_sha) or not clean:
        raise AbstentionAnalysisError("abstention_analysis_requires_clean_commit")
    analyzed_at = clock()
    if analyzed_at.tzinfo is None or analyzed_at.utcoffset() != UTC.utcoffset(analyzed_at):
        raise AbstentionAnalysisError("abstention_analysis_clock_invalid")

    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")
    inference = (inference_runner or run_october_inference)(
        root=root,
        transformer_report=transformer,
        split_manifest=split,
        settings=database_settings,
    )
    _validate_inference(inference, calibration)
    probabilities = probabilities_from_logits(inference.logits, temperature=temperature)
    reproduction = (reproduction_validator or validate_october_reproduction)(
        probabilities,
        inference.labels,
        calibration,
    )
    threshold_results = evaluate_thresholds(probabilities, inference.labels)
    selection = select_threshold(threshold_results)
    class_counts = Counter(LABELS[int(label)] for label in inference.labels)
    report = {
        "report_version": REPORT_VERSION,
        "run_id": run_id,
        "analyzed_at_utc": analyzed_at.isoformat().replace("+00:00", "Z"),
        "source": {**source_hashes, "analysis_implementation_commit_sha": commit_sha},
        "data": {
            "evaluation_split": "validation",
            "evaluation_start_inclusive": EVALUATION_START,
            "evaluation_end_exclusive": EVALUATION_END,
            "record_count": int(inference.labels.size),
            "labels": list(LABELS),
            "class_counts": {label: class_counts[label] for label in LABELS},
            "queried_splits": ["validation"],
            "september_accessed": False,
            "test_accessed": False,
        },
        "policy": {
            "adr": "docs/decisions/0016-proposed-abstention-and-final-evaluation-policy.md",
            "reference_threshold": REFERENCE_THRESHOLD,
            "candidate_thresholds": list(CANDIDATE_THRESHOLDS),
            "comparison_operator": "confidence_greater_than_or_equal_to_threshold",
            "requirements": {
                "minimum_selective_accuracy": MINIMUM_SELECTIVE_ACCURACY,
                "minimum_coverage": MINIMUM_COVERAGE,
                "maximum_false_suggestion_rate": MAXIMUM_FALSE_SUGGESTION_RATE,
                "minimum_actual_class_coverage": MINIMUM_ACTUAL_CLASS_COVERAGE,
                "minimum_predicted_class_suggestions": MINIMUM_PREDICTED_CLASS_SUGGESTIONS,
                "minimum_predicted_class_precision": MINIMUM_PREDICTED_CLASS_PRECISION,
            },
            "selection_order": [
                "highest_global_coverage",
                "highest_global_selective_accuracy",
                "lowest_false_suggestion_rate",
                "lower_threshold",
            ],
            "no_eligible_candidate_fallback": "manual_review_only",
        },
        "reproduction": dict(reproduction),
        "thresholds": threshold_results,
        "selection": selection,
        "runtime": {
            "gpu_inference_seconds": inference.elapsed_seconds,
            "peak_cuda_bytes": inference.peak_cuda_bytes,
        },
        "software": dict((software_reader or _software_versions)()),
        "checks": {
            "source_identity_reconciled": True,
            "artifacts_verified_before_load": True,
            "accepted_october_evidence_reproduced": True,
            "october_counts_reconcile": True,
            "fixed_threshold_grid_used": True,
            "probabilities_finite_and_normalized": True,
            "september_accessed": False,
            "test_accessed": False,
        },
        "limitations": [
            "october_was_used_for_prior_model_selection_and_calibration_assessment",
            "threshold_results_are_validation_tuning_evidence",
            "one_global_threshold_may_affect_classes_differently",
            "wilson_intervals_do_not_cover_distribution_shift_or_label_error",
            "operational_slices_are_not_demographic_fairness_evidence",
            "reviewer_productivity_and_downstream_harm_are_not_measured",
            "frozen_test_remains_untouched",
        ],
        "claims": {
            "threshold_proposed": selection["proposed_threshold"] is not None,
            "threshold_owner_approved": False,
            "test_used_for_threshold_selection": False,
            "deployment_authorized": False,
            "portfolio_promotion_approved": False,
            "interpretation": "validation_only_abstention_policy_tuning",
        },
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_row_logits": False,
            "contains_row_probabilities": False,
            "contains_row_predictions": False,
            "contains_row_threshold_outcomes": False,
            "contains_token_ids": False,
            "report_git_tracking_allowed": True,
        },
    }
    _validate_report(report, root)
    _atomic_json(report_path, report)
    return report


def evaluate_thresholds(probabilities: np.ndarray, labels: np.ndarray) -> list[dict[str, Any]]:
    """Evaluate the fixed reference and candidate threshold grid."""

    _validate_probability_arrays(probabilities, labels)
    predictions = probabilities.argmax(axis=1)
    confidence = probabilities.max(axis=1)
    total = int(labels.size)
    results = []
    for threshold in ALL_THRESHOLDS:
        suggested = confidence >= threshold
        suggested_count = int(suggested.sum())
        correct = suggested & (predictions == labels)
        correct_count = int(correct.sum())
        incorrect_count = suggested_count - correct_count
        coverage = suggested_count / total
        selective_accuracy = correct_count / suggested_count if suggested_count else None
        actual_classes = _actual_class_evidence(labels, predictions, suggested)
        predicted_classes = _predicted_class_evidence(labels, predictions, suggested)
        actual_coverages = [item["coverage"] for item in actual_classes]
        predicted_counts = [item["suggestion_count"] for item in predicted_classes]
        predicted_precisions = [
            item["precision"] if item["precision"] is not None else 0.0
            for item in predicted_classes
        ]
        is_candidate = threshold in CANDIDATE_THRESHOLDS
        checks = {
            "candidate_threshold": is_candidate,
            "selective_accuracy_at_least_0p93": (
                selective_accuracy is not None and selective_accuracy >= MINIMUM_SELECTIVE_ACCURACY
            ),
            "coverage_at_least_0p60": coverage >= MINIMUM_COVERAGE,
            "false_suggestion_rate_at_most_0p05": (
                incorrect_count / total <= MAXIMUM_FALSE_SUGGESTION_RATE
            ),
            "every_actual_class_coverage_at_least_0p10": (
                min(actual_coverages) >= MINIMUM_ACTUAL_CLASS_COVERAGE
            ),
            "every_predicted_class_has_at_least_20_suggestions": (
                min(predicted_counts) >= MINIMUM_PREDICTED_CLASS_SUGGESTIONS
            ),
            "every_predicted_class_precision_at_least_0p50": (
                min(predicted_precisions) >= MINIMUM_PREDICTED_CLASS_PRECISION
            ),
        }
        matrix = np.zeros((len(LABELS), len(LABELS)), dtype=np.int64)
        np.add.at(matrix, (labels[suggested], predictions[suggested]), 1)
        results.append(
            {
                "threshold": threshold,
                "role": "candidate" if is_candidate else "no_abstention_reference",
                "suggested_count": suggested_count,
                "review_count": total - suggested_count,
                "correct_suggestion_count": correct_count,
                "false_suggestion_count": incorrect_count,
                "coverage": coverage,
                "review_rate": 1.0 - coverage,
                "selective_accuracy": selective_accuracy,
                "selective_accuracy_wilson_95": wilson_interval(correct_count, suggested_count),
                "selective_risk": (
                    1.0 - selective_accuracy if selective_accuracy is not None else None
                ),
                "false_suggestion_rate": incorrect_count / total,
                "correct_suggestion_rate": correct_count / total,
                "macro_actual_class_coverage": float(np.mean(actual_coverages)),
                "worst_actual_class_coverage": min(actual_coverages),
                "minimum_predicted_class_suggestions": min(predicted_counts),
                "worst_predicted_class_precision": min(predicted_precisions),
                "actual_classes": actual_classes,
                "predicted_classes": predicted_classes,
                "suggested_confusion_matrix": {
                    "label_order": list(LABELS),
                    "rows": matrix.tolist(),
                },
                "checks": checks,
                "eligible": all(checks.values()),
            }
        )
    return results


def select_threshold(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply the accepted ordered rule or return the manual-review fallback."""

    if [item.get("threshold") for item in results] != list(ALL_THRESHOLDS):
        raise AbstentionAnalysisError("abstention_threshold_grid_invalid")
    eligible = [item for item in results if item.get("eligible") is True]
    if not eligible:
        return {
            "status": "manual_review_only",
            "proposed_threshold": None,
            "eligible_candidate_count": 0,
            "selected_threshold_owner_approved": False,
            "failed_gates_by_threshold": {
                _threshold_key(float(item["threshold"])): [
                    name for name, passed in item["checks"].items() if not passed
                ]
                for item in results
                if item["role"] == "candidate"
            },
            "next_gate": "review_policy_failure_before_any_new_proposal",
        }
    selected = sorted(
        eligible,
        key=lambda item: (
            -float(item["coverage"]),
            -float(item["selective_accuracy"]),
            float(item["false_suggestion_rate"]),
            float(item["threshold"]),
        ),
    )[0]
    return {
        "status": "threshold_proposed",
        "proposed_threshold": selected["threshold"],
        "eligible_candidate_count": len(eligible),
        "selected_threshold_owner_approved": False,
        "failed_gates_by_threshold": {
            _threshold_key(float(item["threshold"])): [
                name for name, passed in item["checks"].items() if not passed
            ]
            for item in results
            if item["role"] == "candidate" and not item["eligible"]
        },
        "next_gate": "owner_review_and_explicit_threshold_approval",
    }


def wilson_interval(successes: int, total: int) -> dict[str, float] | None:
    """Return the two-sided Wilson 95% interval for a binomial proportion."""

    if (
        isinstance(successes, bool)
        or isinstance(total, bool)
        or not isinstance(successes, int)
        or not isinstance(total, int)
        or successes < 0
        or total < 0
        or successes > total
    ):
        raise AbstentionAnalysisError("abstention_wilson_counts_invalid")
    if total == 0:
        return None
    proportion = successes / total
    z_squared = WILSON_Z_95**2
    denominator = 1.0 + z_squared / total
    centre = (proportion + z_squared / (2 * total)) / denominator
    margin = (
        WILSON_Z_95
        * math.sqrt(proportion * (1.0 - proportion) / total + z_squared / (4 * total * total))
        / denominator
    )
    return {"lower": max(0.0, centre - margin), "upper": min(1.0, centre + margin)}


def validate_october_reproduction(
    probabilities: np.ndarray,
    labels: np.ndarray,
    calibration: Mapping[str, Any],
) -> dict[str, Any]:
    """Require October inference to reproduce accepted calibrated aggregates."""

    _validate_probability_arrays(probabilities, labels)
    accepted = calibration["results"]["calibration_evaluation"]["after"]
    predictions = probabilities.argmax(axis=1)
    correct = predictions == labels
    selected = probabilities[np.arange(labels.size), labels]
    nll = float(-np.log(np.clip(selected, 1e-15, 1.0)).mean())
    one_hot = np.eye(len(LABELS), dtype=np.float64)[labels]
    brier = float(np.square(probabilities - one_hot).sum(axis=1).mean())
    observed = {
        "record_count": int(labels.size),
        "accuracy": float(correct.mean()),
        "negative_log_likelihood": nll,
        "multiclass_brier_loss": brier,
    }
    checks = {
        "record_count_matches": observed["record_count"] == accepted["record_count"],
        "accuracy_matches": math.isclose(
            observed["accuracy"],
            accepted["accuracy"],
            rel_tol=0.0,
            abs_tol=REPRODUCTION_ABSOLUTE_TOLERANCE,
        ),
        "negative_log_likelihood_matches": math.isclose(
            observed["negative_log_likelihood"],
            accepted["negative_log_likelihood"],
            rel_tol=0.0,
            abs_tol=REPRODUCTION_ABSOLUTE_TOLERANCE,
        ),
        "multiclass_brier_loss_matches": math.isclose(
            observed["multiclass_brier_loss"],
            accepted["multiclass_brier_loss"],
            rel_tol=0.0,
            abs_tol=REPRODUCTION_ABSOLUTE_TOLERANCE,
        ),
    }
    if not all(checks.values()):
        raise AbstentionAnalysisError("abstention_october_evidence_not_reproduced")
    return {
        "accepted_metrics": {
            name: accepted[name]
            for name in (
                "record_count",
                "accuracy",
                "negative_log_likelihood",
                "multiclass_brier_loss",
            )
        },
        "observed_metrics": observed,
        "absolute_tolerance": REPRODUCTION_ABSOLUTE_TOLERANCE,
        "checks": checks,
    }


def run_october_inference(
    *,
    root: Path,
    transformer_report: Mapping[str, Any],
    split_manifest: Mapping[str, Any],
    settings: DatabaseSettings,
) -> AbstentionInference:
    """Run the accepted MiniLM on October validation rows and no other period."""

    try:
        import torch
        from safetensors.torch import load_file
    except ImportError as error:
        raise AbstentionAnalysisError("abstention_analysis_dependency_missing") from error
    if (
        torch.__version__ != "2.13.0+cu130"
        or not torch.cuda.is_available()
        or torch.version.cuda != "13.0"
        or torch.cuda.get_device_capability(0) != (12, 0)
    ):
        raise AbstentionAnalysisError("abstention_analysis_cuda_boundary_mismatch")
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
            root / transformer_report["artifacts"]["best_model"]["relative_path"],
            device="cuda",
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
        raise AbstentionAnalysisError("abstention_analysis_model_load_failed") from error
    features = tokenize_rows(iter_october_rows(split_manifest, settings), tokenizer)
    batches = length_grouped_batches(
        features,
        batch_size=int(transformer_report["optimization"]["per_device_batch_size"]),
        pool_size=LENGTH_GROUP_POOL_SIZE,
        seed=RANDOM_SEED,
    )
    logits_parts: list[np.ndarray] = []
    label_parts: list[np.ndarray] = []
    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    try:
        with torch.inference_mode():
            for features_batch in batches:
                batch = collate_dynamic(features_batch, tokenizer, return_tensors="pt")
                labels = batch["labels"].to("cuda", non_blocking=True)
                inputs = {
                    key: value.to("cuda", non_blocking=True)
                    for key, value in batch.items()
                    if key != "labels"
                }
                with torch.amp.autocast("cuda", dtype=torch.float16):
                    logits = model(**inputs).logits
                if not torch.isfinite(logits).all():
                    raise AbstentionAnalysisError("abstention_analysis_logits_nonfinite")
                logits_parts.append(logits.float().cpu().numpy().astype(np.float64))
                label_parts.append(labels.cpu().numpy().astype(np.int64))
        return AbstentionInference(
            logits=np.concatenate(logits_parts),
            labels=np.concatenate(label_parts),
            elapsed_seconds=round(time.perf_counter() - started, 3),
            peak_cuda_bytes=int(torch.cuda.max_memory_allocated()),
        )
    except AbstentionAnalysisError:
        raise
    except TransformerDatasetError as error:
        raise AbstentionAnalysisError(error.code, **error.details) from error
    except (OSError, RuntimeError, ValueError) as error:
        raise AbstentionAnalysisError("abstention_analysis_inference_failed") from error
    finally:
        del model
        torch.cuda.empty_cache()


def iter_october_rows(
    manifest: Mapping[str, Any], settings: DatabaseSettings
) -> Iterable[tuple[str, str]]:
    """Stream only included October validation narratives and labels."""

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
          AND o.split_assignment = 'validation'
          AND s.date_received >= DATE '2024-10-01'
          AND s.date_received < DATE '2024-11-01'
        ORDER BY o.raw_batch_id, o.source_row_ordinal
    """
    parameters = (manifest["run_id"], SPLIT_VERSION, POPULATION_VERSION)
    try:
        with psycopg.connect(settings.psycopg_conninfo()) as connection:
            with connection.cursor(name=f"abstention_october_{uuid.uuid4().hex}") as cursor:
                cursor.execute(query, parameters)
                while rows := cursor.fetchmany(FETCH_SIZE):
                    yield from rows
    except psycopg.Error as error:
        raise AbstentionAnalysisError("abstention_analysis_database_failed") from error


def _actual_class_evidence(
    labels: np.ndarray, predictions: np.ndarray, suggested: np.ndarray
) -> list[dict[str, Any]]:
    results = []
    for class_id, label in enumerate(LABELS):
        actual = labels == class_id
        support = int(actual.sum())
        class_suggested = actual & suggested
        suggested_count = int(class_suggested.sum())
        correct_count = int((class_suggested & (predictions == class_id)).sum())
        results.append(
            {
                "label": label,
                "support": support,
                "suggested_count": suggested_count,
                "coverage": suggested_count / support,
                "correct_suggestion_count": correct_count,
                "conditional_accuracy": (
                    correct_count / suggested_count if suggested_count else None
                ),
            }
        )
    return results


def _predicted_class_evidence(
    labels: np.ndarray, predictions: np.ndarray, suggested: np.ndarray
) -> list[dict[str, Any]]:
    results = []
    for class_id, label in enumerate(LABELS):
        predicted = (predictions == class_id) & suggested
        count = int(predicted.sum())
        correct = int((predicted & (labels == class_id)).sum())
        results.append(
            {
                "label": label,
                "suggestion_count": count,
                "correct_count": correct,
                "precision": correct / count if count else None,
                "precision_wilson_95": wilson_interval(correct, count),
            }
        )
    return results


def _validate_inference(inference: AbstentionInference, calibration: Mapping[str, Any]) -> None:
    logits = np.asarray(inference.logits)
    labels = np.asarray(inference.labels)
    if (
        logits.ndim != 2
        or logits.shape != (EXPECTED_RECORD_COUNT, len(LABELS))
        or labels.shape != (EXPECTED_RECORD_COUNT,)
        or not np.issubdtype(labels.dtype, np.integer)
        or np.any((labels < 0) | (labels >= len(LABELS)))
        or not np.isfinite(logits).all()
        or not math.isfinite(inference.elapsed_seconds)
        or inference.elapsed_seconds <= 0
        or isinstance(inference.peak_cuda_bytes, bool)
        or not isinstance(inference.peak_cuda_bytes, int)
        or inference.peak_cuda_bytes <= 0
    ):
        raise AbstentionAnalysisError("abstention_analysis_inference_invalid")
    observed = Counter(LABELS[int(label)] for label in labels)
    expected = next(
        partition["class_counts"]
        for partition in calibration["data"]["partitions"]
        if partition["partition"] == "calibration_evaluation"
    )
    if (
        dict(observed) != expected
        or dict(observed) != EXPECTED_PARTITION_CLASS_COUNTS["calibration_evaluation"]
    ):
        raise AbstentionAnalysisError("abstention_analysis_class_counts_mismatch")


def _validate_probability_arrays(probabilities: np.ndarray, labels: np.ndarray) -> None:
    probabilities = np.asarray(probabilities)
    labels = np.asarray(labels)
    if (
        probabilities.ndim != 2
        or probabilities.shape[1] != len(LABELS)
        or labels.ndim != 1
        or probabilities.shape[0] != labels.size
        or labels.size == 0
        or not np.issubdtype(labels.dtype, np.integer)
        or np.any((labels < 0) | (labels >= len(LABELS)))
        or not np.isfinite(probabilities).all()
        or np.any((probabilities < 0) | (probabilities > 1))
        or not np.allclose(probabilities.sum(axis=1), 1.0, rtol=0.0, atol=1e-12)
    ):
        raise AbstentionAnalysisError("abstention_probability_arrays_invalid")


def _validate_source_identity(
    model_selection: Mapping[str, Any],
    calibration: Mapping[str, Any],
    transformer: Mapping[str, Any],
    split: Mapping[str, Any],
    hashes: Mapping[str, str],
) -> None:
    run_id = model_selection["run_id"]
    if any(report["run_id"] != run_id for report in (calibration, transformer, split)):
        raise AbstentionAnalysisError("abstention_analysis_run_identity_mismatch")
    split_hash = hashes["split_manifest_sha256"]
    if (
        model_selection["source"]["calibration_report_sha256"]
        != hashes["calibration_report_sha256"]
        or model_selection["source"]["transformer_report_sha256"]
        != hashes["transformer_report_sha256"]
        or model_selection["source"]["split_manifest_sha256"] != split_hash
        or calibration["source"]["transformer_report_sha256"] != hashes["transformer_report_sha256"]
        or calibration["source"]["split_manifest_sha256"] != split_hash
        or transformer["source"]["split_manifest_sha256"] != split_hash
        or calibration["source"]["model_artifact_sha256"] != hashes["model_artifact_sha256"]
        or calibration["artifact"]["sha256"] != hashes["calibrator_artifact_sha256"]
    ):
        raise AbstentionAnalysisError("abstention_analysis_source_identity_mismatch")
    if (
        model_selection["decision"]["selected_operational_candidate"] != "calibrated_minilm"
        or not model_selection["decision"]["all_gates_passed"]
        or model_selection["data"]["test_accessed"]
        or calibration["data"]["test_accessed"]
        or transformer["data"]["test_accessed"]
        or not calibration["eligibility"]["calibrator_eligible_for_ct306"]
        or model_selection["claims"]["operational_threshold_selected"]
        or calibration["claims"]["operational_threshold_selected"]
    ):
        raise AbstentionAnalysisError("abstention_analysis_source_boundary_invalid")
    if any(
        report["data"]["labels"] != list(LABELS)
        for report in (model_selection, calibration, transformer)
    ):
        raise AbstentionAnalysisError("abstention_analysis_taxonomy_mismatch")


def _source_paths(root: Path, run_id: str) -> dict[str, Path]:
    return {
        "calibration": root
        / "data/evaluations/cfpb/calibration"
        / f"{run_id}-{CALIBRATION_REPORT_VERSION}.json",
        "transformer": root
        / "data/evaluations/cfpb/transformer"
        / f"{run_id}-{TRANSFORMER_REPORT_VERSION}.json",
        "split": root / "data/manifests/cfpb/splits" / f"{run_id}-split-1.0.0.json",
    }


def _load_report(
    path: Path,
    expected_parent: Path,
    schema_path: Path,
    expected_version: str,
    name: str,
) -> tuple[dict[str, Any], bytes]:
    if path.resolve().parent != expected_parent.resolve():
        raise AbstentionAnalysisError(f"unsafe_abstention_{name}_report_path")
    try:
        encoded = path.read_bytes()
        report = json.loads(encoded)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AbstentionAnalysisError(f"abstention_{name}_report_unreadable") from error
    if not isinstance(report, dict):
        raise AbstentionAnalysisError(f"abstention_{name}_report_schema_invalid", issue_count=1)
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    observed_version = report.get(
        "report_version", report.get("split_manifest_version", report.get("split_version"))
    )
    if errors or observed_version != expected_version:
        raise AbstentionAnalysisError(
            f"abstention_{name}_report_schema_invalid", issue_count=len(errors)
        )
    return report, encoded


def _verify_artifact(root: Path, metadata: Mapping[str, Any], required_prefix: str) -> None:
    relative = metadata.get("relative_path")
    digest = metadata.get("sha256")
    byte_count = metadata.get("byte_count")
    if (
        not isinstance(relative, str)
        or not relative.startswith(required_prefix)
        or not isinstance(digest, str)
        or not SHA256_PATTERN.fullmatch(digest)
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 1
    ):
        raise AbstentionAnalysisError("abstention_artifact_metadata_invalid")
    path = (root / relative).resolve()
    try:
        path.relative_to((root / required_prefix).resolve())
        if path.stat().st_size != byte_count or _file_sha256(path) != digest:
            raise AbstentionAnalysisError("abstention_artifact_hash_mismatch")
    except (OSError, ValueError) as error:
        raise AbstentionAnalysisError("abstention_artifact_unreadable") from error


def _read_calibrator(
    root: Path, metadata: Mapping[str, Any], calibration: Mapping[str, Any]
) -> float:
    try:
        artifact = json.loads((root / metadata["relative_path"]).read_text(encoding="utf-8"))
        temperature = float(artifact["temperature"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise AbstentionAnalysisError("abstention_calibrator_unreadable") from error
    if (
        not math.isfinite(temperature)
        or temperature <= 0
        or not math.isclose(temperature, float(calibration["method"]["temperature"]), abs_tol=0.0)
        or artifact.get("model_artifact_sha256") != calibration["source"]["model_artifact_sha256"]
        or artifact.get("split_manifest_sha256") != calibration["source"]["split_manifest_sha256"]
    ):
        raise AbstentionAnalysisError("abstention_calibrator_identity_mismatch")
    return temperature


def _load_existing_report(path: Path, root: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AbstentionAnalysisError("abstention_report_unreadable") from error
    _validate_report(report, root)
    return report


def _validate_report(report: Mapping[str, Any], root: Path) -> None:
    try:
        schema = json.loads(
            (root / "contracts/cfpb-abstention-analysis.schema.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise AbstentionAnalysisError("abstention_schema_unreadable") from error
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise AbstentionAnalysisError("abstention_report_schema_invalid", issue_count=len(errors))


def _software_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "numpy": version("numpy"),
        "torch": version("torch"),
        "transformers": version("transformers"),
        "safetensors": version("safetensors"),
    }


def _threshold_key(threshold: float) -> str:
    return f"{threshold:.2f}"


def _report_path(root: Path, run_id: str) -> Path:
    return root / "data/evaluations/cfpb/abstention" / f"{run_id}-{REPORT_VERSION}.json"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as destination:
            destination.write(encoded)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise AbstentionAnalysisError("abstention_report_write_failed") from error
    finally:
        temporary.unlink(missing_ok=True)
