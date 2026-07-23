"""Validation-only TF-IDF logistic-regression model selection."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import psycopg
from jsonschema import Draft202012Validator, FormatChecker
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline

from complaint_triage.analytical_population import POPULATION_VERSION
from complaint_triage.db import DatabaseSettings
from complaint_triage.live_extraction import read_git_lineage
from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.taxonomy import CURRENT_PRODUCT_LABELS
from complaint_triage.temporal_split import SPLIT_SCHEMA_PATH, SPLIT_VERSION

REPORT_VERSION = "tfidf-logreg-selection-1.0.0"
ARTIFACT_VERSION = "tfidf-logreg-pipeline-1.0.0"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-tfidf-logreg-report.schema.json"
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FETCH_SIZE = 2_000
MAX_ITER = 200
TOLERANCE = 1e-3
RANDOM_SEED = 42
SMOKE_ROWS_PER_CLASS = 100

LineageReader = Callable[[Path], tuple[str, bool]]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    c: float
    class_weight: str | None


CANDIDATES = (
    CandidateSpec("c0p5-unweighted", 0.5, None),
    CandidateSpec("c1p0-unweighted", 1.0, None),
    CandidateSpec("c0p5-balanced", 0.5, "balanced"),
    CandidateSpec("c1p0-balanced", 1.0, "balanced"),
)


@dataclass(frozen=True)
class ModelingData:
    train_texts: list[str]
    train_labels: list[str]
    validation_texts: list[str]
    validation_labels: list[str]


class TfidfLogregError(Exception):
    """A controlled modeling failure containing no source row values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_tfidf_logreg_error(error: TfidfLogregError) -> dict[str, Any]:
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


def train_tfidf_logreg(
    split_manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
    lineage_reader: LineageReader = read_git_lineage,
    clock: Clock = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Select on validation only and retain one governed pipeline locally."""

    root = repository_root.resolve()
    manifest, manifest_bytes = _load_split_manifest(split_manifest_path, root)
    split_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    report_path = _report_path(root, manifest["run_id"])
    artifact_path = _artifact_path(root, manifest["run_id"])
    if report_path.exists():
        report = _load_existing_report(report_path)
        if report["source"]["split_manifest_sha256"] != split_sha256:
            raise TfidfLogregError("tfidf_report_identity_conflict")
        _verify_existing_artifact(root, report)
        return report

    commit_sha, clean = lineage_reader(root)
    if not SHA40_PATTERN.fullmatch(commit_sha) or not clean:
        raise TfidfLogregError("tfidf_training_requires_clean_commit")
    trained_at = clock()
    if trained_at.tzinfo is None or trained_at.utcoffset() != UTC.utcoffset(trained_at):
        raise TfidfLogregError("tfidf_training_clock_invalid")

    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")
    data = load_modeling_data(manifest, database_settings, smoke=False)
    _reconcile_data(data, manifest)
    result = fit_candidate_search(data, labels=tuple(sorted(CURRENT_PRODUCT_LABELS)))
    selected = result["selected"]
    artifact_metadata = _write_pipeline_artifact(
        artifact_path,
        selected["pipeline"],
        repository_root=root,
    )
    candidates = [_candidate_report(item) for item in result["candidates"]]
    report = {
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
            "train_record_count": len(data.train_labels),
            "validation_record_count": len(data.validation_labels),
            "test_accessed": False,
            "labels": list(sorted(CURRENT_PRODUCT_LABELS)),
        },
        "vectorizer": {
            "kind": "TfidfVectorizer",
            "ngram_range": [1, 2],
            "min_df": 5,
            "max_df": 0.995,
            "max_features": 200_000,
            "sublinear_tf": True,
            "norm": "l2",
            "dtype": "float64",
            "fit_split": "train",
            "feature_count": result["feature_count"],
            "train_matrix_nnz": result["train_matrix_nnz"],
            "validation_matrix_nnz": result["validation_matrix_nnz"],
        },
        "estimator": {
            "kind": "LogisticRegression",
            "solver": "saga",
            "penalty": "l2",
            "max_iter": MAX_ITER,
            "tol": TOLERANCE,
            "random_seed": RANDOM_SEED,
        },
        "selection": {
            "split": "validation",
            "candidate_order": [spec.candidate_id for spec in CANDIDATES],
            "eligibility": "converged_only",
            "ranking": [
                "highest_validation_macro_f1",
                "highest_validation_worst_class_recall",
                "highest_validation_weighted_f1",
                "lower_c",
                "stable_candidate_id",
            ],
            "selected_candidate_id": selected["spec"].candidate_id,
        },
        "candidates": candidates,
        "artifact": artifact_metadata,
        "software": {
            "scikit_learn": version("scikit-learn"),
            "numpy": version("numpy"),
            "scipy": version("scipy"),
            "joblib": version("joblib"),
        },
        "checks": {
            "source_counts_reconcile": True,
            "taxonomy_complete": True,
            "vectorizer_fit_on_train_only": True,
            "selection_uses_validation_only": True,
            "test_accessed": False,
            "all_candidates_converged": all(item["converged"] for item in result["candidates"]),
            "selected_artifact_hashed": True,
        },
        "claims": {
            "portfolio_promotion_approved": False,
            "test_used_for_training_or_tuning": False,
            "interpretation": "validation_selected_baseline_not_final_test_evidence",
        },
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_vocabulary": False,
            "artifact_contains_governed_vocabulary": True,
            "artifact_git_tracking_allowed": False,
            "report_git_tracking_allowed": True,
        },
    }
    _validate_report(report)
    _atomic_json(report_path, report)
    return report


def smoke_tfidf_logreg(
    split_manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
) -> dict[str, Any]:
    """Fit one bounded training-only sample without retaining evidence."""

    root = repository_root.resolve()
    manifest, _ = _load_split_manifest(split_manifest_path, root)
    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")
    data = load_modeling_data(manifest, database_settings, smoke=True)
    if data.validation_texts or data.validation_labels:
        raise TfidfLogregError("tfidf_smoke_accessed_nontraining_data")
    labels = sorted(set(data.train_labels))
    if len(labels) < 2:
        raise TfidfLogregError("tfidf_smoke_requires_multiple_classes")
    vectorizer = build_vectorizer(min_df=1)
    matrix = vectorizer.fit_transform(data.train_texts)
    estimator = build_estimator(CANDIDATES[0])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        estimator.fit(matrix, data.train_labels)
    converged = not any(issubclass(item.category, ConvergenceWarning) for item in caught)
    if not converged:
        raise TfidfLogregError("tfidf_smoke_did_not_converge")
    return {
        "status": "ok",
        "mode": "training_only_smoke",
        "record_count": len(data.train_labels),
        "class_count": len(labels),
        "feature_count": int(matrix.shape[1]),
        "test_accessed": False,
        "validation_accessed": False,
        "artifact_written": False,
        "report_written": False,
        "privacy": {"contains_narratives": False, "contains_vocabulary": False},
    }


def build_vectorizer(*, min_df: int = 5) -> TfidfVectorizer:
    return TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=min_df,
        max_df=0.995,
        max_features=200_000,
        sublinear_tf=True,
        norm="l2",
        dtype=np.float64,
    )


def build_estimator(spec: CandidateSpec) -> LogisticRegression:
    return LogisticRegression(
        C=spec.c,
        class_weight=spec.class_weight,
        solver="saga",
        penalty="l2",
        random_state=RANDOM_SEED,
        max_iter=MAX_ITER,
        tol=TOLERANCE,
    )


def fit_candidate_search(data: ModelingData, *, labels: tuple[str, ...]) -> dict[str, Any]:
    """Fit the fixed search sequentially with a train-only vocabulary."""

    if not data.train_texts or not data.validation_texts:
        raise TfidfLogregError("tfidf_modeling_data_empty")
    if set(data.train_labels) != set(labels) or set(data.validation_labels) != set(labels):
        raise TfidfLogregError("tfidf_modeling_taxonomy_incomplete")
    vectorizer = build_vectorizer()
    train_matrix = vectorizer.fit_transform(data.train_texts)
    validation_matrix = vectorizer.transform(data.validation_texts)
    candidate_results: list[dict[str, Any]] = []
    for spec in CANDIDATES:
        estimator = build_estimator(spec)
        started = time.perf_counter()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ConvergenceWarning)
            estimator.fit(train_matrix, data.train_labels)
        elapsed = time.perf_counter() - started
        converged = not any(issubclass(item.category, ConvergenceWarning) for item in caught)
        predictions = estimator.predict(validation_matrix)
        metrics = classification_metrics(data.validation_labels, predictions, labels)
        candidate_results.append(
            {
                "spec": spec,
                "converged": converged,
                "n_iter": [int(value) for value in estimator.n_iter_],
                "fit_seconds": elapsed,
                "metrics": metrics,
                "pipeline": Pipeline([("tfidf", vectorizer), ("classifier", estimator)]),
            }
        )
    selected = select_candidate(candidate_results)
    return {
        "candidates": candidate_results,
        "selected": selected,
        "feature_count": int(train_matrix.shape[1]),
        "train_matrix_nnz": int(train_matrix.nnz),
        "validation_matrix_nnz": int(validation_matrix.nnz),
    }


def select_candidate(candidates: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Apply the accepted convergence gate and ordered validation tie-breaks."""

    eligible = [candidate for candidate in candidates if candidate["converged"]]
    if not eligible:
        raise TfidfLogregError("tfidf_no_converged_candidate")
    return min(
        eligible,
        key=lambda item: (
            -float(item["metrics"]["macro_f1"]),
            -float(item["metrics"]["worst_class_recall"]),
            -float(item["metrics"]["weighted_f1"]),
            float(item["spec"].c),
            str(item["spec"].candidate_id),
        ),
    )


def classification_metrics(
    actual: Sequence[str], predicted: Sequence[str], labels: tuple[str, ...]
) -> dict[str, Any]:
    precision, recall, f1, support = precision_recall_fscore_support(
        actual, predicted, labels=labels, zero_division=0
    )
    matrix = confusion_matrix(actual, predicted, labels=labels)
    per_class = {
        label: {
            "support": int(support[index]),
            "precision": _score(precision[index]),
            "recall": _score(recall[index]),
            "f1": _score(f1[index]),
        }
        for index, label in enumerate(labels)
    }
    return {
        "record_count": len(actual),
        "accuracy": float(accuracy_score(actual, predicted)),
        "macro_f1": float(f1_score(actual, predicted, labels=labels, average="macro")),
        "worst_class_recall": float(min(recall)),
        "weighted_f1": float(f1_score(actual, predicted, labels=labels, average="weighted")),
        "per_class": per_class,
        "confusion_matrix": {
            "orientation": "rows_actual_columns_predicted",
            "labels": list(labels),
            "rows": matrix.astype(int).tolist(),
        },
    }


def load_modeling_data(
    manifest: Mapping[str, Any], settings: DatabaseSettings, *, smoke: bool
) -> ModelingData:
    """Read only approved training/validation rows; smoke reads training only."""

    train_texts: list[str] = []
    train_labels: list[str] = []
    validation_texts: list[str] = []
    validation_labels: list[str] = []
    try:
        with psycopg.connect(settings.psycopg_conninfo()) as connection:
            if smoke:
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
                    SELECT narrative, target_product, 'train'
                    FROM ranked WHERE class_row <= %s
                    ORDER BY target_product, class_row
                """
                parameters: tuple[Any, ...] = (
                    manifest["run_id"],
                    SPLIT_VERSION,
                    POPULATION_VERSION,
                    SMOKE_ROWS_PER_CLASS,
                )
            else:
                query = """
                    SELECT s.narrative, p.target_product, o.split_assignment
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
                      AND o.split_assignment = ANY(%s)
                    ORDER BY o.split_assignment, o.raw_batch_id, o.source_row_ordinal
                """
                parameters = (
                    manifest["run_id"],
                    SPLIT_VERSION,
                    POPULATION_VERSION,
                    ["train", "validation"],
                )
            with connection.cursor(name=f"tfidf_rows_{uuid.uuid4().hex}") as cursor:
                cursor.execute(query, parameters)
                while rows := cursor.fetchmany(FETCH_SIZE):
                    for narrative, label, split_name in rows:
                        if not isinstance(narrative, str) or not narrative.strip():
                            raise TfidfLogregError("tfidf_source_row_invalid")
                        if label not in CURRENT_PRODUCT_LABELS:
                            raise TfidfLogregError("tfidf_source_taxonomy_invalid")
                        if split_name == "train":
                            train_texts.append(narrative)
                            train_labels.append(label)
                        elif split_name == "validation" and not smoke:
                            validation_texts.append(narrative)
                            validation_labels.append(label)
                        else:
                            raise TfidfLogregError("tfidf_unapproved_split_returned")
    except TfidfLogregError:
        raise
    except psycopg.Error as error:
        raise TfidfLogregError("tfidf_database_failed") from error
    return ModelingData(train_texts, train_labels, validation_texts, validation_labels)


def _reconcile_data(data: ModelingData, manifest: Mapping[str, Any]) -> None:
    expected = manifest["class_counts_by_split"]
    for split_name, observed_labels in (
        ("train", data.train_labels),
        ("validation", data.validation_labels),
    ):
        observed = {label: observed_labels.count(label) for label in CURRENT_PRODUCT_LABELS}
        if observed != expected[split_name]:
            raise TfidfLogregError("tfidf_source_counts_do_not_reconcile", split=split_name)


def _candidate_report(candidate: Mapping[str, Any]) -> dict[str, Any]:
    metrics = candidate["metrics"]
    return {
        "candidate_id": candidate["spec"].candidate_id,
        "c": candidate["spec"].c,
        "class_weight": candidate["spec"].class_weight,
        "converged": candidate["converged"],
        "n_iter": candidate["n_iter"],
        "fit_seconds": round(float(candidate["fit_seconds"]), 3),
        "validation": {
            "record_count": metrics["record_count"],
            "accuracy": _score(metrics["accuracy"]),
            "macro_f1": _score(metrics["macro_f1"]),
            "worst_class_recall": _score(metrics["worst_class_recall"]),
            "weighted_f1": _score(metrics["weighted_f1"]),
            "per_class": metrics["per_class"],
            "confusion_matrix": metrics["confusion_matrix"],
        },
    }


def _load_split_manifest(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    resolved = path.resolve()
    if resolved.parent != (root / "data" / "manifests" / "cfpb" / "splits").resolve():
        raise TfidfLogregError("unsafe_split_manifest_path")
    try:
        encoded = resolved.read_bytes()
        manifest = json.loads(encoded)
        schema = json.loads(SPLIT_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TfidfLogregError("tfidf_split_manifest_unreadable") from error
    if not isinstance(manifest, dict):
        raise TfidfLogregError("tfidf_split_manifest_schema_invalid")
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)
    )
    if errors:
        raise TfidfLogregError("tfidf_split_manifest_schema_invalid", issue_count=len(errors))
    return manifest, encoded


def _report_path(root: Path, run_id: str) -> Path:
    return (
        root / "data" / "evaluations" / "cfpb" / "tfidf-logreg" / f"{run_id}-{REPORT_VERSION}.json"
    )


def _artifact_path(root: Path, run_id: str) -> Path:
    return root / "artifacts" / "cfpb" / "tfidf-logreg" / run_id / f"{ARTIFACT_VERSION}.joblib"


def _write_pipeline_artifact(
    path: Path, pipeline: Pipeline, *, repository_root: Path
) -> dict[str, Any]:
    resolved = path.resolve()
    artifact_root = (repository_root / "artifacts").resolve()
    if artifact_root not in resolved.parents:
        raise TfidfLogregError("unsafe_tfidf_artifact_path")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        joblib.dump(pipeline, temporary, compress=3)
        with temporary.open("rb+") as artifact:
            artifact.flush()
            os.fsync(artifact.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise TfidfLogregError("tfidf_artifact_write_failed") from error
    finally:
        temporary.unlink(missing_ok=True)
    relative = path.resolve().relative_to(repository_root).as_posix()
    return {
        "version": ARTIFACT_VERSION,
        "relative_path": relative,
        "sha256": _file_sha256(path),
        "byte_count": path.stat().st_size,
        "retention": "local_only_governed_until_2026-11-19",
    }


def _verify_existing_artifact(root: Path, report: Mapping[str, Any]) -> None:
    metadata = report["artifact"]
    path = (root / metadata["relative_path"]).resolve()
    if (root / "artifacts").resolve() not in path.parents:
        raise TfidfLogregError("unsafe_tfidf_artifact_path")
    if not path.is_file() or path.stat().st_size != metadata["byte_count"]:
        raise TfidfLogregError("tfidf_artifact_missing_or_changed")
    if _file_sha256(path) != metadata["sha256"]:
        raise TfidfLogregError("tfidf_artifact_missing_or_changed")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_existing_report(path: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TfidfLogregError("tfidf_report_unreadable") from error
    if not isinstance(report, dict):
        raise TfidfLogregError("tfidf_report_schema_invalid")
    _validate_report(report)
    return report


def _validate_report(report: Mapping[str, Any]) -> None:
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise TfidfLogregError("tfidf_report_schema_invalid", issue_count=len(errors))


def _score(value: float) -> float:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise TfidfLogregError("tfidf_metric_invalid")
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
