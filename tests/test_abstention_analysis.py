import inspect
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.abstention_analysis import (
    ALL_THRESHOLDS,
    REPORT_VERSION,
    AbstentionAnalysisError,
    AbstentionInference,
    analyze_abstention_thresholds,
    evaluate_thresholds,
    iter_october_rows,
    select_threshold,
    wilson_interval,
)
from complaint_triage.db import DatabaseSettings
from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.transformer_calibration import EXPECTED_PARTITION_CLASS_COUNTS
from complaint_triage.transformer_dataset import LABELS

RUN_ID = "cfpb-run-20260722T130728Z-2b7815d4c850"
MODEL_SELECTION_NAME = f"{RUN_ID}-operational-model-selection-1.0.0.json"
MODEL_SELECTION_SOURCE = (
    PROJECT_ROOT / "data/evaluations/cfpb/model-selection" / MODEL_SELECTION_NAME
)
FIXED_CLOCK = "2026-07-25T12:00:00+00:00"
FIXED_SHA = "a" * 40
SETTINGS = DatabaseSettings(database="test", user="test", password="test")


def _copy_sources(root: Path) -> Path:
    source_paths = (
        MODEL_SELECTION_SOURCE,
        PROJECT_ROOT
        / "data/evaluations/cfpb/calibration"
        / f"{RUN_ID}-transformer-temperature-calibration-1.0.0.json",
        PROJECT_ROOT
        / "data/evaluations/cfpb/transformer"
        / f"{RUN_ID}-transformer-minilm-selection-1.0.0.json",
        PROJECT_ROOT / "data/manifests/cfpb/splits" / f"{RUN_ID}-split-1.0.0.json",
    )
    schema_paths = (
        PROJECT_ROOT / "contracts/cfpb-model-selection.schema.json",
        PROJECT_ROOT / "contracts/cfpb-transformer-calibration.schema.json",
        PROJECT_ROOT / "contracts/cfpb-transformer-training.schema.json",
        PROJECT_ROOT / "contracts/cfpb-temporal-split-manifest.schema.json",
        PROJECT_ROOT / "contracts/cfpb-abstention-analysis.schema.json",
    )
    for source in (*source_paths, *schema_paths):
        destination = root / source.relative_to(PROJECT_ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return root / MODEL_SELECTION_SOURCE.relative_to(PROJECT_ROOT)


def _inference(confidence: float) -> AbstentionInference:
    counts = EXPECTED_PARTITION_CLASS_COUNTS["calibration_evaluation"]
    labels = np.concatenate(
        [np.full(counts[label], class_id, dtype=np.int64) for class_id, label in enumerate(LABELS)]
    )
    probabilities = np.full(
        (labels.size, len(LABELS)),
        (1.0 - confidence) / (len(LABELS) - 1),
        dtype=np.float64,
    )
    probabilities[np.arange(labels.size), labels] = confidence
    return AbstentionInference(
        logits=np.log(probabilities),
        labels=labels,
        elapsed_seconds=12.5,
        peak_cuda_bytes=1_234,
    )


def _reproduction(*_args) -> dict:
    metrics = {
        "record_count": 41_831,
        "accuracy": 1.0,
        "negative_log_likelihood": 0.1,
        "multiclass_brier_loss": 0.01,
    }
    return {
        "accepted_metrics": metrics,
        "observed_metrics": metrics,
        "absolute_tolerance": 0.00001,
        "checks": {
            "record_count_matches": True,
            "accuracy_matches": True,
            "negative_log_likelihood_matches": True,
            "multiclass_brier_loss_matches": True,
        },
    }


def _software() -> dict[str, str]:
    return {
        "python": "3.12.0",
        "numpy": "2.0.0",
        "torch": "2.13.0+cu130",
        "transformers": "5.0.0",
        "safetensors": "0.6.0",
    }


def _analyze(root: Path, inference: AbstentionInference, *, clean: bool = True) -> dict:
    from datetime import datetime

    model_selection = _copy_sources(root)
    return analyze_abstention_thresholds(
        model_selection,
        repository_root=root,
        settings=SETTINGS,
        lineage_reader=lambda _root: (FIXED_SHA, clean),
        clock=lambda: datetime.fromisoformat(FIXED_CLOCK),
        artifact_verifier=lambda *_args: None,
        calibrator_reader=lambda *_args: 1.0,
        inference_runner=lambda **_kwargs: inference,
        reproduction_validator=_reproduction,
        software_reader=_software,
    )


def test_analysis_writes_closed_validation_only_report_and_replays(tmp_path) -> None:
    report = _analyze(tmp_path, _inference(0.96))

    assert report["report_version"] == REPORT_VERSION
    assert report["data"]["queried_splits"] == ["validation"]
    assert report["data"]["september_accessed"] is False
    assert report["data"]["test_accessed"] is False
    assert report["selection"]["status"] == "threshold_proposed"
    assert report["selection"]["proposed_threshold"] == 0.5
    assert report["selection"]["selected_threshold_owner_approved"] is False
    assert report["claims"]["portfolio_promotion_approved"] is False
    assert len(report["thresholds"]) == len(ALL_THRESHOLDS)

    report_path = tmp_path / "data/evaluations/cfpb/abstention" / f"{RUN_ID}-{REPORT_VERSION}.json"
    encoded = report_path.read_bytes()
    assert encoded.endswith(b"\n")
    schema = json.loads(
        (tmp_path / "contracts/cfpb-abstention-analysis.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)

    replay = analyze_abstention_thresholds(
        tmp_path / MODEL_SELECTION_SOURCE.relative_to(PROJECT_ROOT),
        repository_root=tmp_path,
        settings=SETTINGS,
        artifact_verifier=lambda *_args: None,
        calibrator_reader=lambda *_args: 1.0,
        inference_runner=lambda **_kwargs: pytest.fail("replay reran inference"),
    )
    assert replay == report


def test_analysis_falls_back_to_manual_review_when_no_candidate_is_eligible(tmp_path) -> None:
    report = _analyze(tmp_path, _inference(0.40))

    assert report["selection"]["status"] == "manual_review_only"
    assert report["selection"]["proposed_threshold"] is None
    assert report["selection"]["eligible_candidate_count"] == 0
    assert report["claims"]["threshold_proposed"] is False
    assert all(not item["eligible"] for item in report["thresholds"])


def test_analysis_requires_clean_implementation_commit_before_inference(tmp_path) -> None:
    model_selection = _copy_sources(tmp_path)

    with pytest.raises(AbstentionAnalysisError) as captured:
        analyze_abstention_thresholds(
            model_selection,
            repository_root=tmp_path,
            settings=SETTINGS,
            lineage_reader=lambda _root: (FIXED_SHA, False),
            artifact_verifier=lambda *_args: None,
            calibrator_reader=lambda *_args: 1.0,
            inference_runner=lambda **_kwargs: pytest.fail("dirty run reached inference"),
        )

    assert captured.value.code == "abstention_analysis_requires_clean_commit"


def test_threshold_boundary_is_inclusive_and_grid_is_fixed() -> None:
    probabilities = np.zeros((len(LABELS), len(LABELS)), dtype=np.float64)
    labels = np.arange(len(LABELS), dtype=np.int64)
    for class_id in labels:
        probabilities[class_id, class_id] = 0.5
        probabilities[class_id, (class_id + 1) % len(LABELS)] = 0.5

    results = evaluate_thresholds(probabilities, labels)
    threshold_050 = next(item for item in results if item["threshold"] == 0.5)

    assert threshold_050["suggested_count"] == len(LABELS)
    with pytest.raises(AbstentionAnalysisError, match="abstention_threshold_grid_invalid"):
        select_threshold(results[:-1])


def test_wilson_interval_handles_empty_and_validates_counts() -> None:
    assert wilson_interval(0, 0) is None
    interval = wilson_interval(5, 10)
    assert interval is not None
    assert interval["lower"] < 0.5 < interval["upper"]
    with pytest.raises(AbstentionAnalysisError, match="abstention_wilson_counts_invalid"):
        wilson_interval(11, 10)


def test_october_query_source_excludes_test_and_september_boundaries() -> None:
    source = inspect.getsource(iter_october_rows)

    assert "o.split_assignment = 'validation'" in source
    assert "DATE '2024-10-01'" in source
    assert "DATE '2024-11-01'" in source
    assert "o.split_assignment = 'test'" not in source
    assert "DATE '2024-09-01'" not in source
