"""Governed validation-only comparison of the accepted model candidates."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.live_extraction import read_git_lineage
from complaint_triage.real_extraction import PROJECT_ROOT

REPORT_VERSION = "validation-model-comparison-1.0.0"
BASELINE_REPORT_VERSION = "tfidf-logreg-selection-1.0.0"
TRANSFORMER_REPORT_VERSION = "transformer-minilm-selection-1.0.0"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-validation-model-comparison.schema.json"
BASELINE_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-tfidf-logreg-report.schema.json"
TRANSFORMER_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-transformer-training.schema.json"
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHARED_METRICS = ("accuracy", "macro_f1", "weighted_f1", "worst_class_recall")
CLASS_METRICS = ("precision", "recall", "f1")

LineageReader = Callable[[Path], tuple[str, bool]]
Clock = Callable[[], datetime]


class ValidationComparisonError(Exception):
    """A controlled comparison failure containing no row-level values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_validation_comparison_error(error: ValidationComparisonError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "complaint_ids_logged": False,
            "row_values_in_report": False,
            "vocabulary_logged": False,
            "token_ids_logged": False,
        },
    }


def compare_validation_models(
    baseline_report_path: Path,
    transformer_report_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    lineage_reader: LineageReader = read_git_lineage,
    clock: Clock = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Compare selected candidates using only their accepted validation evidence."""

    root = repository_root.resolve()
    baseline, baseline_bytes = _load_source_report(
        baseline_report_path,
        root / "data" / "evaluations" / "cfpb" / "tfidf-logreg",
        BASELINE_SCHEMA_PATH,
        BASELINE_REPORT_VERSION,
        "baseline",
    )
    transformer, transformer_bytes = _load_source_report(
        transformer_report_path,
        root / "data" / "evaluations" / "cfpb" / "transformer",
        TRANSFORMER_SCHEMA_PATH,
        TRANSFORMER_REPORT_VERSION,
        "transformer",
    )
    _validate_shared_identity(baseline, transformer)

    baseline_sha256 = hashlib.sha256(baseline_bytes).hexdigest()
    transformer_sha256 = hashlib.sha256(transformer_bytes).hexdigest()
    report_path = _report_path(root, baseline["run_id"])
    if report_path.exists():
        existing = _load_existing_report(report_path)
        source = existing["source"]
        if (
            source["baseline_report_sha256"] != baseline_sha256
            or source["transformer_report_sha256"] != transformer_sha256
        ):
            raise ValidationComparisonError("validation_comparison_report_identity_conflict")
        return existing

    commit_sha, clean = lineage_reader(root)
    if not SHA40_PATTERN.fullmatch(commit_sha) or not clean:
        raise ValidationComparisonError("validation_comparison_requires_clean_commit")
    compared_at = clock()
    if compared_at.tzinfo is None or compared_at.utcoffset() != UTC.utcoffset(compared_at):
        raise ValidationComparisonError("validation_comparison_clock_invalid")

    baseline_candidate = _selected_baseline_candidate(baseline)
    transformer_epoch = _selected_transformer_epoch(transformer)
    baseline_metrics = baseline_candidate["validation"]
    transformer_metrics = transformer_epoch["validation"]["metrics"]
    shared_metrics = {
        metric: _metric_comparison(baseline_metrics[metric], transformer_metrics[metric])
        for metric in SHARED_METRICS
    }
    if any(result["winner"] != "transformer" for result in shared_metrics.values()):
        raise ValidationComparisonError("validation_comparison_quality_proposal_not_supported")
    per_class = _per_class_comparison(
        baseline_metrics["per_class"], transformer_metrics["per_class"], baseline["data"]["labels"]
    )
    f1_wins = _winner_counts(per_class)
    baseline_bytes_count = baseline["artifact"]["byte_count"]
    transformer_bytes_count = transformer["artifacts"]["best_model"]["byte_count"]

    report = {
        "report_version": REPORT_VERSION,
        "run_id": baseline["run_id"],
        "compared_at_utc": compared_at.isoformat().replace("+00:00", "Z"),
        "source": {
            "baseline_report_sha256": baseline_sha256,
            "transformer_report_sha256": transformer_sha256,
            "split_manifest_sha256": baseline["source"]["split_manifest_sha256"],
            "comparison_implementation_commit_sha": commit_sha,
        },
        "data": {
            "evaluation_split": "validation",
            "train_record_count": baseline["data"]["train_record_count"],
            "validation_record_count": baseline["data"]["validation_record_count"],
            "labels": baseline["data"]["labels"],
            "test_accessed": False,
        },
        "models": {
            "baseline": {
                "model_family": "tfidf_logistic_regression",
                "selected_candidate_id": baseline_candidate["candidate_id"],
                "artifact_byte_count": baseline_bytes_count,
                "compute_seconds": baseline_candidate["fit_seconds"],
                "compute_scope": "selected_candidate_fit_only",
            },
            "transformer": {
                "model_family": "minilm_full_fine_tune",
                "selected_epoch": transformer_epoch["epoch"],
                "artifact_byte_count": transformer_bytes_count,
                "compute_seconds": transformer["runtime"]["summed_epoch_compute_seconds"],
                "compute_scope": "all_completed_training_and_validation_epochs",
            },
        },
        "comparison": {
            "metric_direction": "higher_is_better",
            "shared_validation_metrics": shared_metrics,
            "per_class": per_class,
            "class_f1_wins": f1_wins,
            "artifact_footprint": {
                "baseline_byte_count": baseline_bytes_count,
                "transformer_byte_count": transformer_bytes_count,
                "transformer_minus_baseline_bytes": transformer_bytes_count - baseline_bytes_count,
                "transformer_to_baseline_ratio": round(
                    transformer_bytes_count / baseline_bytes_count, 6
                ),
            },
            "non_comparable_evidence": {
                "top_2_accuracy": "transformer_only",
                "calibration": "not_yet_measured",
                "selective_accuracy_after_abstention": "not_yet_measured",
                "cpu_inference_latency": "not_yet_measured",
                "runtime_memory": "not_comparable_across_models",
                "explainability": "not_yet_assessed_under_fixed_rule",
                "operational_complexity": "not_yet_assessed_under_fixed_rule",
                "deployment_cost": "not_yet_assessed_under_fixed_rule",
            },
        },
        "utility_proposal": {
            "status": "advance_transformer_to_ct305_calibration",
            "basis": "validation_quality_only",
            "candidate_for_calibration": "transformer_minilm",
            "final_operational_model": None,
            "final_decision_gate": "ct306_written_utility_adr",
            "rationale": [
                "transformer_has_higher_validation_macro_f1",
                "transformer_has_higher_validation_worst_class_recall",
                "transformer_has_higher_validation_weighted_f1",
                "transformer_has_higher_validation_accuracy",
            ],
            "unresolved_dimensions": [
                "calibration",
                "selective_accuracy_after_abstention",
                "cpu_inference_latency",
                "runtime_memory",
                "explainability",
                "operational_complexity",
                "deployment_cost",
            ],
        },
        "checks": {
            "run_identity_matches": True,
            "split_identity_matches": True,
            "train_counts_match": True,
            "validation_counts_match": True,
            "labels_match": True,
            "per_class_support_matches": True,
            "selected_candidates_reconciled": True,
            "source_reports_validation_only": True,
            "test_accessed": False,
        },
        "limitations": [
            "validation_was_used_for_model_selection",
            "baseline_metrics_are_rounded_to_six_decimals",
            "training_compute_scopes_are_not_comparable",
            "top_2_accuracy_is_available_only_for_transformer",
            "calibration_and_abstention_are_deferred_to_ct305",
            "latency_memory_explainability_complexity_and_cost_are_deferred_to_ct306",
            "no_final_operational_model_selected_in_ct304",
        ],
        "claims": {
            "portfolio_promotion_approved": False,
            "test_used_for_comparison": False,
            "operational_model_selected": False,
            "interpretation": "validation_only_candidate_comparison",
        },
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_vocabulary": False,
            "contains_token_ids": False,
            "git_tracking_allowed": True,
        },
    }
    _validate_report(report)
    _atomic_json(report_path, report)
    return report


def _load_source_report(
    path: Path,
    expected_parent: Path,
    schema_path: Path,
    expected_version: str,
    source_name: str,
) -> tuple[dict[str, Any], bytes]:
    resolved = path.resolve()
    if resolved.parent != expected_parent.resolve():
        raise ValidationComparisonError(f"unsafe_validation_comparison_{source_name}_report_path")
    try:
        encoded = resolved.read_bytes()
        report = json.loads(encoded)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationComparisonError(
            f"validation_comparison_{source_name}_report_unreadable"
        ) from error
    if not isinstance(report, dict):
        raise ValidationComparisonError(
            f"validation_comparison_{source_name}_report_schema_invalid"
        )
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors or report.get("report_version") != expected_version:
        raise ValidationComparisonError(
            f"validation_comparison_{source_name}_report_schema_invalid",
            issue_count=len(errors),
        )
    return report, encoded


def _validate_shared_identity(baseline: Mapping[str, Any], transformer: Mapping[str, Any]) -> None:
    comparisons = {
        "run_identity": baseline["run_id"] == transformer["run_id"],
        "split_identity": baseline["source"]["split_manifest_sha256"]
        == transformer["source"]["split_manifest_sha256"],
        "train_counts": baseline["data"]["train_record_count"]
        == transformer["data"]["train_record_count"],
        "validation_counts": baseline["data"]["validation_record_count"]
        == transformer["data"]["validation_record_count"],
        "labels": baseline["data"]["labels"] == transformer["data"]["labels"],
        "feature_input": baseline["data"]["feature_input"] == transformer["data"]["feature_input"],
    }
    failed = [name for name, matches in comparisons.items() if not matches]
    if failed:
        raise ValidationComparisonError(
            "validation_comparison_source_identity_mismatch", field=failed[0]
        )
    if (
        baseline["data"]["test_accessed"]
        or transformer["data"]["test_accessed"]
        or baseline["checks"]["test_accessed"]
        or transformer["checks"]["test_accessed"]
        or baseline["claims"]["test_used_for_training_or_tuning"]
        or transformer["claims"]["test_used_for_training_or_tuning"]
    ):
        raise ValidationComparisonError("validation_comparison_test_boundary_violated")


def _selected_baseline_candidate(report: Mapping[str, Any]) -> Mapping[str, Any]:
    selected_id = report["selection"]["selected_candidate_id"]
    selected = [item for item in report["candidates"] if item["candidate_id"] == selected_id]
    if len(selected) != 1 or not selected[0]["converged"]:
        raise ValidationComparisonError("validation_comparison_baseline_selection_invalid")
    return selected[0]


def _selected_transformer_epoch(report: Mapping[str, Any]) -> Mapping[str, Any]:
    selected_epoch = report["selection"]["selected_epoch"]
    selected = [item for item in report["epochs"] if item["epoch"] == selected_epoch]
    if len(selected) != 1:
        raise ValidationComparisonError("validation_comparison_transformer_selection_invalid")
    return selected[0]


def _metric_comparison(baseline: float, transformer: float) -> dict[str, float | str]:
    if not all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in (baseline, transformer)):
        raise ValidationComparisonError("validation_comparison_metric_invalid")
    return {
        "baseline": baseline,
        "transformer": transformer,
        "delta_transformer_minus_baseline": transformer - baseline,
        "winner": _winner(baseline, transformer),
    }


def _per_class_comparison(
    baseline: Mapping[str, Any], transformer: Mapping[str, Any], labels: list[str]
) -> list[dict[str, Any]]:
    if set(baseline) != set(labels) or set(transformer) != set(labels):
        raise ValidationComparisonError("validation_comparison_per_class_labels_mismatch")
    result = []
    for label in labels:
        left = baseline[label]
        right = transformer[label]
        if left["support"] != right["support"]:
            raise ValidationComparisonError(
                "validation_comparison_per_class_support_mismatch", label=label
            )
        result.append(
            {
                "label": label,
                "support": left["support"],
                "baseline": {metric: left[metric] for metric in CLASS_METRICS},
                "transformer": {metric: right[metric] for metric in CLASS_METRICS},
                "delta_transformer_minus_baseline": {
                    metric: right[metric] - left[metric] for metric in CLASS_METRICS
                },
                "f1_winner": _winner(left["f1"], right["f1"]),
            }
        )
    return result


def _winner(baseline: float, transformer: float) -> str:
    if transformer > baseline:
        return "transformer"
    if transformer < baseline:
        return "baseline"
    return "tie"


def _winner_counts(per_class: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        winner: sum(item["f1_winner"] == winner for item in per_class)
        for winner in ("baseline", "transformer", "tie")
    }


def _load_existing_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationComparisonError("validation_comparison_report_unreadable") from error
    if not isinstance(report, dict):
        raise ValidationComparisonError("validation_comparison_report_schema_invalid")
    _validate_report(report)
    return report


def _validate_report(report: Mapping[str, Any]) -> None:
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise ValidationComparisonError(
            "validation_comparison_report_schema_invalid", issue_count=len(errors)
        )


def _report_path(root: Path, run_id: str) -> Path:
    return (
        root
        / "data"
        / "evaluations"
        / "cfpb"
        / "model-comparison"
        / f"{run_id}-{REPORT_VERSION}.json"
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
    finally:
        temporary.unlink(missing_ok=True)
