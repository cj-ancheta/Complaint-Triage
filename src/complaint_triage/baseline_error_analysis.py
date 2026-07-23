"""Aggregate validation-only error analysis for the accepted TF-IDF baseline."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import psycopg
from jsonschema import Draft202012Validator, FormatChecker
from sklearn.pipeline import Pipeline

from complaint_triage.analytical_population import POPULATION_VERSION
from complaint_triage.db import DatabaseSettings
from complaint_triage.live_extraction import read_git_lineage
from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.taxonomy import CURRENT_PRODUCT_LABELS
from complaint_triage.temporal_split import SPLIT_SCHEMA_PATH, SPLIT_VERSION
from complaint_triage.tfidf_logreg import (
    REPORT_SCHEMA_PATH as MODEL_REPORT_SCHEMA_PATH,
)
from complaint_triage.tfidf_logreg import classification_metrics

REPORT_VERSION = "baseline-error-analysis-1.0.0"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-baseline-error-analysis.schema.json"
MODEL_REPORT_VERSION = "tfidf-logreg-selection-1.0.0"
EXPECTED_MONTHS = ("2024-09", "2024-10")
RARE_TRAINING_SHARE = 0.01
TOP_CONFUSION_LIMIT = 20
FETCH_SIZE = 2_000
SCORE_BATCH_SIZE = 2_000
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")

LineageReader = Callable[[Path], tuple[str, bool]]
Clock = Callable[[], datetime]
ArtifactLoader = Callable[[Path], Any]


@dataclass(frozen=True)
class ValidationData:
    narratives: list[str]
    labels: list[str]
    received_dates: list[date]
    narrative_char_counts: list[int]


class BaselineErrorAnalysisError(Exception):
    """A controlled diagnostic failure containing no source row values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_baseline_error(error: BaselineErrorAnalysisError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "complaint_ids_logged": False,
            "row_values_in_report": False,
            "vocabulary_logged": False,
        },
    }


def analyze_baseline_errors(
    model_report_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
    lineage_reader: LineageReader = read_git_lineage,
    clock: Clock = lambda: datetime.now(UTC),
    artifact_loader: ArtifactLoader = joblib.load,
) -> dict[str, Any]:
    """Score validation only and publish closed aggregate diagnostic evidence."""

    root = repository_root.resolve()
    model_report, model_report_bytes = _load_model_report(model_report_path, root)
    model_report_sha256 = hashlib.sha256(model_report_bytes).hexdigest()
    run_id = model_report["run_id"]
    report_path = _report_path(root, run_id)
    if report_path.exists():
        existing = _load_existing_report(report_path)
        if existing["source"]["model_report_sha256"] != model_report_sha256:
            raise BaselineErrorAnalysisError("error_analysis_report_identity_conflict")
        return existing

    commit_sha, clean = lineage_reader(root)
    if not SHA40_PATTERN.fullmatch(commit_sha) or not clean:
        raise BaselineErrorAnalysisError("error_analysis_requires_clean_commit")
    analyzed_at = clock()
    if analyzed_at.tzinfo is None or analyzed_at.utcoffset() != UTC.utcoffset(analyzed_at):
        raise BaselineErrorAnalysisError("error_analysis_clock_invalid")

    split_manifest, split_bytes = _load_split_manifest(root, run_id)
    split_sha256 = hashlib.sha256(split_bytes).hexdigest()
    if split_sha256 != model_report["source"]["split_manifest_sha256"]:
        raise BaselineErrorAnalysisError("error_analysis_split_identity_mismatch")
    pipeline = load_verified_pipeline(
        root,
        model_report,
        artifact_loader=artifact_loader,
    )
    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")
    data = load_validation_data(run_id, database_settings)
    _reconcile_source(data, model_report)
    predictions, top2_correct = score_validation(pipeline, data.narratives, data.labels)
    labels = tuple(model_report["data"]["labels"])
    analysis = build_error_analysis(
        actual=data.labels,
        predicted=predictions,
        top2_correct=top2_correct,
        received_dates=data.received_dates,
        narrative_char_counts=data.narrative_char_counts,
        labels=labels,
        training_counts=split_manifest["class_counts_by_split"]["train"],
    )
    _reconcile_selected_metrics(analysis["overall"], model_report)
    report = {
        "report_version": REPORT_VERSION,
        "run_id": run_id,
        "analyzed_at_utc": analyzed_at.isoformat().replace("+00:00", "Z"),
        "source": {
            "model_report_sha256": model_report_sha256,
            "model_artifact_sha256": model_report["artifact"]["sha256"],
            "split_manifest_sha256": split_sha256,
            "selected_candidate_id": model_report["selection"]["selected_candidate_id"],
            "analysis_implementation_commit_sha": commit_sha,
        },
        "data": {
            "evaluation_split": "validation",
            "record_count": len(data.labels),
            "months": list(EXPECTED_MONTHS),
            "labels": list(labels),
            "test_accessed": False,
        },
        "slice_definitions": {
            "temporal": "calendar_month",
            "narrative_length_unit": "staging_narrative_character_count",
            "narrative_length_bands": [
                {"band_id": "chars-1-499", "minimum_inclusive": 1, "maximum_inclusive": 499},
                {
                    "band_id": "chars-500-999",
                    "minimum_inclusive": 500,
                    "maximum_inclusive": 999,
                },
                {
                    "band_id": "chars-1000-1999",
                    "minimum_inclusive": 1_000,
                    "maximum_inclusive": 1_999,
                },
                {
                    "band_id": "chars-2000-3999",
                    "minimum_inclusive": 2_000,
                    "maximum_inclusive": 3_999,
                },
                {
                    "band_id": "chars-4000-plus",
                    "minimum_inclusive": 4_000,
                    "maximum_inclusive": None,
                },
            ],
            "rare_class_definition": "training_share_below_0.01",
            "top_confusion_limit": TOP_CONFUSION_LIMIT,
        },
        "analysis": analysis,
        "software": {
            "scikit_learn": version("scikit-learn"),
            "numpy": version("numpy"),
            "scipy": version("scipy"),
            "joblib": version("joblib"),
        },
        "checks": {
            "source_counts_reconcile": True,
            "selected_metrics_reproduced": True,
            "artifact_verified_before_load": True,
            "all_validation_rows_scored_once": True,
            "temporal_slices_reconcile": True,
            "length_slices_reconcile": True,
            "test_accessed": False,
        },
        "limitations": [
            "validation_was_used_for_model_selection",
            "temporal_analysis_covers_only_two_months",
            "submission_channel_unavailable_in_accepted_staging_contract",
            "window_contains_single_post_transition_taxonomy",
            "operational_slices_are_not_demographic_fairness_evidence",
            "no_narrative_level_examples_published_due_to_retention_policy",
            "no_calibration_or_abstention_decision_in_ct206",
        ],
        "claims": {
            "portfolio_promotion_approved": False,
            "test_used_for_analysis": False,
            "model_selection_changed": False,
            "demographic_fairness_assessed": False,
            "interpretation": "validation_only_descriptive_error_analysis",
        },
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_vocabulary": False,
            "contains_token_linked_coefficients": False,
            "git_tracking_allowed": True,
        },
    }
    _validate_report(report)
    _atomic_json(report_path, report)
    return report


def load_verified_pipeline(
    root: Path,
    model_report: Mapping[str, Any],
    *,
    artifact_loader: ArtifactLoader = joblib.load,
) -> Pipeline:
    """Verify identity, size, hash, and software before deserialization."""

    metadata = model_report["artifact"]
    path = (root / metadata["relative_path"]).resolve()
    artifact_root = (root / "artifacts").resolve()
    if artifact_root not in path.parents:
        raise BaselineErrorAnalysisError("unsafe_error_analysis_artifact_path")
    if not path.is_file() or path.stat().st_size != metadata["byte_count"]:
        raise BaselineErrorAnalysisError("error_analysis_artifact_missing_or_changed")
    if _file_sha256(path) != metadata["sha256"]:
        raise BaselineErrorAnalysisError("error_analysis_artifact_missing_or_changed")
    current_versions = {
        "scikit_learn": version("scikit-learn"),
        "numpy": version("numpy"),
        "scipy": version("scipy"),
        "joblib": version("joblib"),
    }
    for package, current in current_versions.items():
        if model_report["software"][package] != current:
            raise BaselineErrorAnalysisError(
                "error_analysis_software_version_mismatch", package=package
            )
    try:
        pipeline = artifact_loader(path)
    except Exception as error:
        raise BaselineErrorAnalysisError("error_analysis_artifact_load_failed") from error
    if not isinstance(pipeline, Pipeline):
        raise BaselineErrorAnalysisError("error_analysis_artifact_contract_invalid")
    if set(pipeline.named_steps) != {"tfidf", "classifier"}:
        raise BaselineErrorAnalysisError("error_analysis_artifact_contract_invalid")
    return pipeline


def load_validation_data(run_id: str, settings: DatabaseSettings) -> ValidationData:
    """Load only included validation rows and approved diagnostic fields."""

    narratives: list[str] = []
    labels: list[str] = []
    received_dates: list[date] = []
    char_counts: list[int] = []
    try:
        with psycopg.connect(settings.psycopg_conninfo()) as connection:
            with connection.cursor(name=f"error_analysis_{uuid.uuid4().hex}") as cursor:
                cursor.execute(
                    """
                    SELECT s.narrative, p.target_product, s.date_received,
                           p.narrative_char_count
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
                    ORDER BY s.date_received, o.raw_batch_id, o.source_row_ordinal
                    """,
                    (run_id, SPLIT_VERSION, POPULATION_VERSION),
                )
                while rows := cursor.fetchmany(FETCH_SIZE):
                    for narrative, label, received, char_count in rows:
                        if not isinstance(narrative, str) or not narrative.strip():
                            raise BaselineErrorAnalysisError("error_analysis_source_row_invalid")
                        if label not in CURRENT_PRODUCT_LABELS:
                            raise BaselineErrorAnalysisError("error_analysis_source_row_invalid")
                        if not isinstance(received, date):
                            raise BaselineErrorAnalysisError("error_analysis_source_row_invalid")
                        if type(char_count) is not int or char_count < 1:
                            raise BaselineErrorAnalysisError("error_analysis_source_row_invalid")
                        narratives.append(narrative)
                        labels.append(label)
                        received_dates.append(received)
                        char_counts.append(char_count)
    except BaselineErrorAnalysisError:
        raise
    except psycopg.Error as error:
        raise BaselineErrorAnalysisError("error_analysis_database_failed") from error
    return ValidationData(narratives, labels, received_dates, char_counts)


def score_validation(
    pipeline: Pipeline, narratives: Sequence[str], actual: Sequence[str]
) -> tuple[list[str], list[bool]]:
    """Score in bounded batches and retain no text-derived row output."""

    if len(narratives) != len(actual) or not narratives:
        raise BaselineErrorAnalysisError("error_analysis_scoring_input_invalid")
    vectorizer = pipeline.named_steps["tfidf"]
    classifier = pipeline.named_steps["classifier"]
    classes = np.asarray(classifier.classes_)
    predictions: list[str] = []
    top2_correct: list[bool] = []
    for start in range(0, len(narratives), SCORE_BATCH_SIZE):
        stop = min(start + SCORE_BATCH_SIZE, len(narratives))
        matrix = vectorizer.transform(narratives[start:stop])
        probabilities = classifier.predict_proba(matrix)
        predicted_indices = np.argmax(probabilities, axis=1)
        predictions.extend(str(classes[index]) for index in predicted_indices)
        top2_indices = np.argpartition(probabilities, -2, axis=1)[:, -2:]
        top2_correct.extend(
            str(actual[start + row_index]) in classes[indexes]
            for row_index, indexes in enumerate(top2_indices)
        )
    return predictions, top2_correct


def build_error_analysis(
    *,
    actual: Sequence[str],
    predicted: Sequence[str],
    top2_correct: Sequence[bool],
    received_dates: Sequence[date],
    narrative_char_counts: Sequence[int],
    labels: tuple[str, ...],
    training_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Build deterministic per-class, temporal, length, and rarity aggregates."""

    lengths = {
        len(actual),
        len(predicted),
        len(top2_correct),
        len(received_dates),
        len(narrative_char_counts),
    }
    if len(lengths) != 1 or not actual:
        raise BaselineErrorAnalysisError("error_analysis_inputs_do_not_reconcile")
    if set(actual) != set(labels) or set(predicted) - set(labels):
        raise BaselineErrorAnalysisError("error_analysis_taxonomy_invalid")

    overall = _slice_metrics(actual, predicted, top2_correct, labels)
    matrix = overall["confusion_matrix"]["rows"]
    total_errors = overall["error_count"]
    if total_errors <= 0:
        raise BaselineErrorAnalysisError("error_analysis_has_no_errors")
    confusions: list[dict[str, Any]] = []
    for actual_index, actual_label in enumerate(labels):
        actual_errors = (
            overall["per_class"][actual_label]["support"] - matrix[actual_index][actual_index]
        )
        for predicted_index, predicted_label in enumerate(labels):
            if actual_index == predicted_index:
                continue
            count = matrix[actual_index][predicted_index]
            if count:
                confusions.append(
                    {
                        "actual_label": actual_label,
                        "predicted_label": predicted_label,
                        "count": count,
                        "share_of_all_errors": _score(count / total_errors),
                        "share_of_actual_class_errors": _score(count / actual_errors),
                    }
                )
    confusions.sort(
        key=lambda item: (-item["count"], item["actual_label"], item["predicted_label"])
    )

    months = [received.strftime("%Y-%m") for received in received_dates]
    if set(months) != set(EXPECTED_MONTHS):
        raise BaselineErrorAnalysisError("error_analysis_temporal_boundary_invalid")
    temporal = [
        {
            "month": month,
            **_indexed_slice(actual, predicted, top2_correct, labels, months, month),
        }
        for month in EXPECTED_MONTHS
    ]
    band_ids = [_length_band(value) for value in narrative_char_counts]
    length_bands = [
        {
            "band_id": band_id,
            **_indexed_slice(actual, predicted, top2_correct, labels, band_ids, band_id),
        }
        for band_id in (
            "chars-1-499",
            "chars-500-999",
            "chars-1000-1999",
            "chars-2000-3999",
            "chars-4000-plus",
        )
    ]
    if sum(item["record_count"] for item in temporal) != len(actual):
        raise BaselineErrorAnalysisError("error_analysis_temporal_counts_do_not_reconcile")
    if sum(item["record_count"] for item in length_bands) != len(actual):
        raise BaselineErrorAnalysisError("error_analysis_length_counts_do_not_reconcile")

    training_total = sum(training_counts.values())
    if set(training_counts) != set(labels) or training_total <= 0:
        raise BaselineErrorAnalysisError("error_analysis_training_counts_invalid")
    rare_labels = tuple(
        label for label in labels if training_counts[label] / training_total < RARE_TRAINING_SHARE
    )
    common_labels = tuple(label for label in labels if label not in rare_labels)
    if not rare_labels or not common_labels:
        raise BaselineErrorAnalysisError("error_analysis_rarity_groups_invalid")
    rarity_groups = [
        _rarity_group("rare", rare_labels, overall["per_class"]),
        _rarity_group("common", common_labels, overall["per_class"]),
    ]
    weakest_recall_label = min(
        labels, key=lambda label: (overall["per_class"][label]["recall"], label)
    )
    return {
        "overall": overall,
        "top_confusions": confusions[:TOP_CONFUSION_LIMIT],
        "temporal": temporal,
        "narrative_length": length_bands,
        "rarity_groups": rarity_groups,
        "findings": {
            "weakest_recall_label": weakest_recall_label,
            "weakest_recall": overall["per_class"][weakest_recall_label]["recall"],
            "largest_confusion": confusions[0],
            "monthly_macro_f1_range": _range(item["metrics"]["macro_f1"] for item in temporal),
            "length_band_macro_f1_range": _range(
                item["metrics"]["macro_f1"] for item in length_bands
            ),
        },
    }


def _slice_metrics(
    actual: Sequence[str],
    predicted: Sequence[str],
    top2_correct: Sequence[bool],
    labels: tuple[str, ...],
) -> dict[str, Any]:
    base = classification_metrics(actual, predicted, labels)
    error_count = sum(left != right for left, right in zip(actual, predicted, strict=True))
    return {
        "record_count": len(actual),
        "error_count": error_count,
        "metrics": {
            "accuracy": _score(base["accuracy"]),
            "macro_f1": _score(base["macro_f1"]),
            "worst_class_recall": _score(base["worst_class_recall"]),
            "weighted_f1": _score(base["weighted_f1"]),
            "top2_accuracy": _score(sum(top2_correct) / len(top2_correct)),
        },
        "per_class": base["per_class"],
        "confusion_matrix": base["confusion_matrix"],
    }


def _indexed_slice(
    actual: Sequence[str],
    predicted: Sequence[str],
    top2_correct: Sequence[bool],
    labels: tuple[str, ...],
    group_values: Sequence[str],
    selected_group: str,
) -> dict[str, Any]:
    indexes = [index for index, value in enumerate(group_values) if value == selected_group]
    if not indexes:
        raise BaselineErrorAnalysisError("error_analysis_required_slice_empty")
    sliced = _slice_metrics(
        [actual[index] for index in indexes],
        [predicted[index] for index in indexes],
        [top2_correct[index] for index in indexes],
        labels,
    )
    return {
        "record_count": sliced["record_count"],
        "error_count": sliced["error_count"],
        "metrics": sliced["metrics"],
        "class_support": {label: sliced["per_class"][label]["support"] for label in labels},
        "per_class_recall": {label: sliced["per_class"][label]["recall"] for label in labels},
    }


def _rarity_group(
    group_id: str,
    labels: tuple[str, ...],
    per_class: Mapping[str, Mapping[str, int | float]],
) -> dict[str, Any]:
    return {
        "group_id": group_id,
        "labels": list(labels),
        "validation_support": sum(int(per_class[label]["support"]) for label in labels),
        "macro_precision": _score(
            sum(float(per_class[label]["precision"]) for label in labels) / len(labels)
        ),
        "macro_recall": _score(
            sum(float(per_class[label]["recall"]) for label in labels) / len(labels)
        ),
        "macro_f1": _score(sum(float(per_class[label]["f1"]) for label in labels) / len(labels)),
    }


def _length_band(char_count: int) -> str:
    if 1 <= char_count <= 499:
        return "chars-1-499"
    if char_count <= 999:
        return "chars-500-999"
    if char_count <= 1_999:
        return "chars-1000-1999"
    if char_count <= 3_999:
        return "chars-2000-3999"
    return "chars-4000-plus"


def _range(values: Iterable[float]) -> dict[str, float]:
    materialized = list(values)
    return {
        "minimum": min(materialized),
        "maximum": max(materialized),
        "difference": _score(max(materialized) - min(materialized)),
    }


def _reconcile_source(data: ValidationData, model_report: Mapping[str, Any]) -> None:
    expected_candidate = next(
        candidate
        for candidate in model_report["candidates"]
        if candidate["candidate_id"] == model_report["selection"]["selected_candidate_id"]
    )
    expected_counts = {
        label: metrics["support"]
        for label, metrics in expected_candidate["validation"]["per_class"].items()
    }
    if Counter(data.labels) != expected_counts:
        raise BaselineErrorAnalysisError("error_analysis_source_counts_do_not_reconcile")
    if len(data.labels) != model_report["data"]["validation_record_count"]:
        raise BaselineErrorAnalysisError("error_analysis_source_counts_do_not_reconcile")


def _reconcile_selected_metrics(
    overall: Mapping[str, Any], model_report: Mapping[str, Any]
) -> None:
    selected = next(
        candidate
        for candidate in model_report["candidates"]
        if candidate["candidate_id"] == model_report["selection"]["selected_candidate_id"]
    )["validation"]
    for metric in ("accuracy", "macro_f1", "worst_class_recall", "weighted_f1"):
        if overall["metrics"][metric] != selected[metric]:
            raise BaselineErrorAnalysisError("error_analysis_selected_metrics_do_not_reproduce")
    if overall["per_class"] != selected["per_class"]:
        raise BaselineErrorAnalysisError("error_analysis_selected_metrics_do_not_reproduce")
    if overall["confusion_matrix"] != selected["confusion_matrix"]:
        raise BaselineErrorAnalysisError("error_analysis_selected_metrics_do_not_reproduce")


def _load_model_report(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    resolved = path.resolve()
    expected_parent = (root / "data" / "evaluations" / "cfpb" / "tfidf-logreg").resolve()
    if resolved.parent != expected_parent:
        raise BaselineErrorAnalysisError("unsafe_error_analysis_model_report_path")
    try:
        encoded = resolved.read_bytes()
        report = json.loads(encoded)
        schema = json.loads(MODEL_REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineErrorAnalysisError("error_analysis_model_report_unreadable") from error
    if not isinstance(report, dict):
        raise BaselineErrorAnalysisError("error_analysis_model_report_schema_invalid")
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors or report.get("report_version") != MODEL_REPORT_VERSION:
        raise BaselineErrorAnalysisError(
            "error_analysis_model_report_schema_invalid", issue_count=len(errors)
        )
    return report, encoded


def _load_split_manifest(root: Path, run_id: str) -> tuple[dict[str, Any], bytes]:
    path = root / "data" / "manifests" / "cfpb" / "splits" / f"{run_id}-split-{SPLIT_VERSION}.json"
    try:
        encoded = path.read_bytes()
        manifest = json.loads(encoded)
        schema = json.loads(SPLIT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineErrorAnalysisError("error_analysis_split_manifest_unreadable") from error
    if not isinstance(manifest, dict):
        raise BaselineErrorAnalysisError("error_analysis_split_manifest_schema_invalid")
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)
    )
    if errors:
        raise BaselineErrorAnalysisError(
            "error_analysis_split_manifest_schema_invalid", issue_count=len(errors)
        )
    return manifest, encoded


def _load_existing_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BaselineErrorAnalysisError("error_analysis_report_unreadable") from error
    if not isinstance(report, dict):
        raise BaselineErrorAnalysisError("error_analysis_report_schema_invalid")
    _validate_report(report)
    return report


def _validate_report(report: Mapping[str, Any]) -> None:
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise BaselineErrorAnalysisError(
            "error_analysis_report_schema_invalid", issue_count=len(errors)
        )


def _report_path(root: Path, run_id: str) -> Path:
    return (
        root
        / "data"
        / "evaluations"
        / "cfpb"
        / "error-analysis"
        / f"{run_id}-{REPORT_VERSION}.json"
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _score(value: float) -> float:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise BaselineErrorAnalysisError("error_analysis_metric_invalid")
    return round(float(value), 6)


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
