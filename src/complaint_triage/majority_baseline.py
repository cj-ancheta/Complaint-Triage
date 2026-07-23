"""Training-only majority baseline evaluated from aggregate split counts."""

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
from complaint_triage.taxonomy import CURRENT_PRODUCT_LABELS
from complaint_triage.temporal_split import SPLIT_SCHEMA_PATH, SPLIT_VERSION

REPORT_VERSION = "majority-baseline-1.0.0"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-majority-baseline-report.schema.json"
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SPLIT_NAMES = ("train", "validation", "test")

LineageReader = Callable[[Path], tuple[str, bool]]
Clock = Callable[[], datetime]


class MajorityBaselineError(Exception):
    """A controlled evaluation failure containing no row-level values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_majority_baseline_error(error: MajorityBaselineError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "complaint_ids_logged": False,
            "row_values_in_report": False,
        },
    }


def evaluate_majority_baseline(
    split_manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    lineage_reader: LineageReader = read_git_lineage,
    clock: Clock = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Evaluate a frozen training-majority predictor and publish safe evidence."""

    root = repository_root.resolve()
    split_manifest, split_bytes = _load_split_manifest(split_manifest_path, root)
    split_sha256 = hashlib.sha256(split_bytes).hexdigest()
    labels = tuple(sorted(CURRENT_PRODUCT_LABELS))
    counts_by_split = _validated_counts(split_manifest, labels)
    predicted_label = select_training_majority(counts_by_split["train"])
    evaluation = evaluate_constant_predictor(counts_by_split, predicted_label, labels)
    report_path = (
        root
        / "data"
        / "evaluations"
        / "cfpb"
        / "majority"
        / f"{split_manifest['run_id']}-{REPORT_VERSION}.json"
    )

    if report_path.exists():
        existing = _load_existing_report(report_path)
        if (
            existing.get("source", {}).get("split_manifest_sha256") != split_sha256
            or existing.get("model", {}).get("predicted_label") != predicted_label
            or existing.get("labels") != list(labels)
            or existing.get("evaluation") != evaluation
        ):
            raise MajorityBaselineError("majority_report_identity_conflict")
        return existing

    commit_sha, working_tree_clean = lineage_reader(root)
    if not SHA40_PATTERN.fullmatch(commit_sha) or not working_tree_clean:
        raise MajorityBaselineError("majority_evaluation_requires_clean_commit")
    evaluated_at = clock()
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() != UTC.utcoffset(evaluated_at):
        raise MajorityBaselineError("majority_evaluation_clock_invalid")

    checks = {
        "source_counts_reconcile": True,
        "taxonomy_complete": True,
        "majority_selected_from_train_only": True,
        "all_classes_scored": all(
            set(evaluation[split_name]["per_class"]) == set(labels) for split_name in SPLIT_NAMES
        ),
        "confusion_matrices_reconcile": all(
            sum(sum(row) for row in evaluation[split_name]["confusion_matrix"]["rows"])
            == evaluation[split_name]["record_count"]
            for split_name in SPLIT_NAMES
        ),
        "metrics_finite": all(
            math.isfinite(score)
            for split_name in SPLIT_NAMES
            for score in evaluation[split_name]["metrics"].values()
        ),
    }
    if not all(checks.values()):
        raise MajorityBaselineError(
            "majority_evaluation_reconciliation_failed",
            failed_check_count=sum(not value for value in checks.values()),
        )
    report = {
        "report_version": REPORT_VERSION,
        "run_id": split_manifest["run_id"],
        "evaluated_at_utc": evaluated_at.isoformat().replace("+00:00", "Z"),
        "source": {
            "split_manifest_sha256": split_sha256,
            "split_version": SPLIT_VERSION,
            "split_implementation_commit_sha": split_manifest["source"][
                "split_implementation_commit_sha"
            ],
            "evaluation_implementation_commit_sha": commit_sha,
        },
        "model": {
            "strategy": "predict_training_majority_for_every_row",
            "predicted_label": predicted_label,
            "selection_split": "train",
            "tie_behavior": "fail_closed",
            "feature_input": "none",
            "tunable_parameter_count": 0,
        },
        "labels": list(labels),
        "evaluation": evaluation,
        "checks": checks,
        "claims": {
            "portfolio_promotion_approved": False,
            "test_used_for_tuning": False,
            "interpretation": "non_tunable_reference_baseline",
        },
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "git_tracking_allowed": True,
        },
    }
    _validate_report(report)
    _atomic_json(report_path, report)
    return report


def select_training_majority(training_counts: Mapping[str, int]) -> str:
    """Select the unique largest training class or fail when majority is ambiguous."""

    if not training_counts or any(
        type(value) is not int or value <= 0 for value in training_counts.values()
    ):
        raise MajorityBaselineError("majority_training_counts_invalid")
    largest = max(training_counts.values())
    winners = sorted(label for label, count in training_counts.items() if count == largest)
    if len(winners) != 1:
        raise MajorityBaselineError("majority_label_tie", tied_label_count=len(winners))
    return winners[0]


def evaluate_constant_predictor(
    counts_by_split: Mapping[str, Mapping[str, int]],
    predicted_label: str,
    labels: tuple[str, ...],
) -> dict[str, Any]:
    """Calculate deterministic multiclass metrics for one constant prediction."""

    if predicted_label not in labels:
        raise MajorityBaselineError("majority_label_outside_taxonomy")
    evaluation: dict[str, Any] = {}
    label_count = len(labels)
    for split_name in SPLIT_NAMES:
        counts = counts_by_split.get(split_name)
        if counts is None or set(counts) != set(labels):
            raise MajorityBaselineError("majority_split_counts_invalid")
        total = sum(counts.values())
        if total <= 0:
            raise MajorityBaselineError("majority_split_counts_invalid")
        predicted_index = labels.index(predicted_label)
        per_class: dict[str, dict[str, int | float]] = {}
        matrix: list[list[int]] = []
        raw_precision: dict[str, float] = {}
        raw_recall: dict[str, float] = {}
        raw_f1: dict[str, float] = {}
        for label in labels:
            support = counts[label]
            if type(support) is not int or support <= 0:
                raise MajorityBaselineError("majority_split_counts_invalid")
            is_majority = label == predicted_label
            true_positive = support if is_majority else 0
            false_positive = total - support if is_majority else 0
            false_negative = 0 if is_majority else support
            precision = support / total if is_majority else 0.0
            recall = 1.0 if is_majority else 0.0
            f1 = 2 * precision * recall / (precision + recall) if is_majority else 0.0
            raw_precision[label] = precision
            raw_recall[label] = recall
            raw_f1[label] = f1
            per_class[label] = {
                "support": support,
                "predicted_count": total if is_majority else 0,
                "true_positive": true_positive,
                "false_positive": false_positive,
                "false_negative": false_negative,
                "precision": _score(precision),
                "recall": _score(recall),
                "f1": _score(f1),
            }
            row = [0] * label_count
            row[predicted_index] = support
            matrix.append(row)
        accuracy = counts[predicted_label] / total
        macro_precision = sum(raw_precision.values()) / label_count
        macro_recall = sum(raw_recall.values()) / label_count
        macro_f1 = sum(raw_f1.values()) / label_count
        weighted_f1 = sum(counts[label] * raw_f1[label] for label in labels) / total
        evaluation[split_name] = {
            "record_count": total,
            "class_distribution": dict(sorted(counts.items())),
            "metrics": {
                "accuracy": _score(accuracy),
                "macro_precision": _score(macro_precision),
                "macro_recall": _score(macro_recall),
                "macro_f1": _score(macro_f1),
                "weighted_f1": _score(weighted_f1),
            },
            "per_class": per_class,
            "confusion_matrix": {
                "orientation": "rows_actual_columns_predicted",
                "labels": list(labels),
                "rows": matrix,
            },
        }
    return evaluation


def _validated_counts(
    split_manifest: Mapping[str, Any], labels: tuple[str, ...]
) -> dict[str, dict[str, int]]:
    raw_counts = split_manifest["class_counts_by_split"]
    counts_by_split: dict[str, dict[str, int]] = {}
    for split_name in SPLIT_NAMES:
        counts = raw_counts.get(split_name)
        if not isinstance(counts, dict) or set(counts) != set(labels):
            raise MajorityBaselineError("majority_source_taxonomy_mismatch")
        typed = {str(label): value for label, value in counts.items()}
        if any(type(value) is not int or value <= 0 for value in typed.values()):
            raise MajorityBaselineError("majority_source_counts_invalid")
        if sum(typed.values()) != split_manifest["split_counts"][split_name]:
            raise MajorityBaselineError("majority_source_counts_do_not_reconcile")
        counts_by_split[split_name] = typed
    return counts_by_split


def _load_split_manifest(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    resolved = path.resolve()
    expected_parent = (root / "data" / "manifests" / "cfpb" / "splits").resolve()
    if resolved.parent != expected_parent:
        raise MajorityBaselineError("unsafe_split_manifest_path")
    try:
        encoded = resolved.read_bytes()
        manifest = json.loads(encoded)
        schema = json.loads(SPLIT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MajorityBaselineError("majority_split_manifest_unreadable") from error
    if not isinstance(manifest, dict):
        raise MajorityBaselineError("majority_split_manifest_schema_invalid")
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)
    )
    if errors:
        raise MajorityBaselineError(
            "majority_split_manifest_schema_invalid", issue_count=len(errors)
        )
    return manifest, encoded


def _load_existing_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise MajorityBaselineError("majority_report_unreadable") from error
    if not isinstance(report, dict):
        raise MajorityBaselineError("majority_report_schema_invalid")
    _validate_report(report)
    return report


def _validate_report(report: Mapping[str, Any]) -> None:
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise MajorityBaselineError("majority_report_schema_invalid", issue_count=len(errors))


def _score(value: float) -> float:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise MajorityBaselineError("majority_metric_invalid")
    return round(value, 6)


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
