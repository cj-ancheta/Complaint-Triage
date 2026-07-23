from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path

import pytest
from sklearn.pipeline import Pipeline

from complaint_triage import baseline_error_analysis
from complaint_triage.baseline_error_analysis import (
    BaselineErrorAnalysisError,
    ValidationData,
    analyze_baseline_errors,
    build_error_analysis,
    load_verified_pipeline,
    safe_baseline_error,
)
from complaint_triage.taxonomy import CURRENT_PRODUCT_LABELS


def _synthetic_inputs():
    labels = tuple(sorted(CURRENT_PRODUCT_LABELS))
    actual: list[str] = []
    predicted: list[str] = []
    top2: list[bool] = []
    dates: list[date] = []
    char_counts: list[int] = []
    bands = (100, 600, 1_500, 2_500, 4_500)
    for label_index, label in enumerate(labels):
        for band_index, char_count in enumerate(bands):
            actual.append(label)
            predicted.append(labels[(label_index + 1) % len(labels)] if band_index == 0 else label)
            top2.append(True)
            dates.append(date(2024, 9 if (label_index + band_index) % 2 == 0 else 10, 15))
            char_counts.append(char_count)
    training_counts = {label: 100 for label in labels}
    training_counts[labels[0]] = 1
    return actual, predicted, top2, dates, char_counts, labels, training_counts


def test_build_error_analysis_reconciles_fixed_slices_and_rarity() -> None:
    actual, predicted, top2, dates, char_counts, labels, training_counts = _synthetic_inputs()

    analysis = build_error_analysis(
        actual=actual,
        predicted=predicted,
        top2_correct=top2,
        received_dates=dates,
        narrative_char_counts=char_counts,
        labels=labels,
        training_counts=training_counts,
    )

    assert analysis["overall"]["record_count"] == 55
    assert analysis["overall"]["error_count"] == 11
    assert analysis["overall"]["metrics"]["top2_accuracy"] == 1.0
    assert [item["month"] for item in analysis["temporal"]] == ["2024-09", "2024-10"]
    assert sum(item["record_count"] for item in analysis["temporal"]) == 55
    assert [item["record_count"] for item in analysis["narrative_length"]] == [11] * 5
    assert analysis["rarity_groups"][0]["labels"] == [labels[0]]
    assert analysis["rarity_groups"][1]["group_id"] == "common"
    assert len(analysis["top_confusions"]) == 11


def test_confusion_ranking_is_count_then_stable_labels() -> None:
    actual, predicted, top2, dates, char_counts, labels, training_counts = _synthetic_inputs()

    analysis = build_error_analysis(
        actual=actual,
        predicted=predicted,
        top2_correct=top2,
        received_dates=dates,
        narrative_char_counts=char_counts,
        labels=labels,
        training_counts=training_counts,
    )

    pairs = [(item["actual_label"], item["predicted_label"]) for item in analysis["top_confusions"]]
    assert pairs == sorted(pairs)


def test_artifact_hash_is_checked_before_deserialization(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "cfpb" / "tfidf-logreg" / "run" / "model.joblib"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"synthetic artifact")
    loader_called = False

    def loader(path: Path):
        nonlocal loader_called
        loader_called = True
        return Pipeline([("tfidf", object()), ("classifier", object())])

    model_report = {
        "artifact": {
            "relative_path": artifact.relative_to(tmp_path).as_posix(),
            "byte_count": artifact.stat().st_size,
            "sha256": "0" * 64,
        },
        "software": {
            "scikit_learn": version("scikit-learn"),
            "numpy": version("numpy"),
            "scipy": version("scipy"),
            "joblib": version("joblib"),
        },
    }

    with pytest.raises(
        BaselineErrorAnalysisError, match="error_analysis_artifact_missing_or_changed"
    ):
        load_verified_pipeline(tmp_path, model_report, artifact_loader=loader)
    assert loader_called is False

    model_report["artifact"]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    pipeline = load_verified_pipeline(tmp_path, model_report, artifact_loader=loader)
    assert loader_called is True
    assert isinstance(pipeline, Pipeline)


def test_temporal_boundary_rejects_any_nonvalidation_month() -> None:
    actual, predicted, top2, dates, char_counts, labels, training_counts = _synthetic_inputs()
    dates[0] = date(2024, 11, 1)

    with pytest.raises(
        BaselineErrorAnalysisError, match="error_analysis_temporal_boundary_invalid"
    ):
        build_error_analysis(
            actual=actual,
            predicted=predicted,
            top2_correct=top2,
            received_dates=dates,
            narrative_char_counts=char_counts,
            labels=labels,
            training_counts=training_counts,
        )


def test_safe_error_never_contains_source_values() -> None:
    result = safe_baseline_error(
        BaselineErrorAnalysisError("error_analysis_source_counts_do_not_reconcile")
    )

    assert result["error"] == {"code": "error_analysis_source_counts_do_not_reconcile"}
    assert result["privacy"] == {
        "narratives_logged": False,
        "complaint_ids_logged": False,
        "row_values_in_report": False,
        "vocabulary_logged": False,
    }


def test_source_query_is_validation_only_and_report_has_no_row_fields() -> None:
    root = Path(__file__).parents[1]
    source = (root / "src" / "complaint_triage" / "baseline_error_analysis.py").read_text(
        encoding="utf-8"
    )
    schema = json.loads(
        (root / "contracts" / "cfpb-baseline-error-analysis.schema.json").read_text(
            encoding="utf-8"
        )
    )

    assert "o.split_assignment = 'validation'" in source
    assert "o.split_assignment = 'test'" not in source
    assert schema["properties"]["privacy"]["properties"]["contains_narratives"] == {"const": False}
    assert "complaint_id" not in json.dumps(schema["properties"]["analysis"])


def test_full_synthetic_report_validates_and_replays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = Path(__file__).parents[1]
    source_model_report = next(
        (source_root / "data" / "evaluations" / "cfpb" / "tfidf-logreg").glob("*.json")
    )
    model_report = json.loads(source_model_report.read_text(encoding="utf-8"))
    run_id = model_report["run_id"]
    model_destination = (
        tmp_path / "data" / "evaluations" / "cfpb" / "tfidf-logreg" / source_model_report.name
    )
    model_destination.parent.mkdir(parents=True)
    model_destination.write_text(json.dumps(model_report), encoding="utf-8")
    source_split = (
        source_root / "data" / "manifests" / "cfpb" / "splits" / f"{run_id}-split-1.0.0.json"
    )
    split_destination = tmp_path / "data" / "manifests" / "cfpb" / "splits" / source_split.name
    split_destination.parent.mkdir(parents=True)
    split_destination.write_bytes(source_split.read_bytes())
    actual, predicted, top2, dates, char_counts, _, _ = _synthetic_inputs()
    data = ValidationData(
        narratives=[f"synthetic fixture {index}" for index in range(len(actual))],
        labels=actual,
        received_dates=dates,
        narrative_char_counts=char_counts,
    )
    monkeypatch.setattr(baseline_error_analysis, "load_verified_pipeline", lambda *a, **k: object())
    monkeypatch.setattr(baseline_error_analysis, "load_validation_data", lambda *a, **k: data)
    monkeypatch.setattr(baseline_error_analysis, "_reconcile_source", lambda *a, **k: None)
    monkeypatch.setattr(
        baseline_error_analysis,
        "score_validation",
        lambda *a, **k: (predicted, top2),
    )
    monkeypatch.setattr(
        baseline_error_analysis, "_reconcile_selected_metrics", lambda *a, **k: None
    )

    report = analyze_baseline_errors(
        model_destination,
        repository_root=tmp_path,
        settings=object(),
        lineage_reader=lambda root: ("a" * 40, True),
        clock=lambda: datetime(2026, 7, 23, 14, tzinfo=UTC),
    )

    assert report["data"]["evaluation_split"] == "validation"
    assert report["data"]["test_accessed"] is False
    assert report["analysis"]["overall"]["record_count"] == 55
    assert report["privacy"]["contains_narratives"] is False
    encoded = json.dumps(report)
    assert "synthetic fixture" not in encoded

    replay = analyze_baseline_errors(
        model_destination,
        repository_root=tmp_path,
        settings=object(),
        lineage_reader=lambda root: ("b" * 40, False),
    )
    assert replay == report
