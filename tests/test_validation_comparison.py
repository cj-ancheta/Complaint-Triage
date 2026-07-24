import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from complaint_triage.validation_comparison import (
    REPORT_SCHEMA_PATH,
    ValidationComparisonError,
    compare_validation_models,
    safe_validation_comparison_error,
)


def _copy_accepted_reports(root: Path) -> tuple[Path, Path]:
    source_root = Path(__file__).parents[1]
    baseline_source = next(
        (source_root / "data" / "evaluations" / "cfpb" / "tfidf-logreg").glob("*.json")
    )
    transformer_source = next(
        (source_root / "data" / "evaluations" / "cfpb" / "transformer").glob("*.json")
    )
    baseline = root / "data" / "evaluations" / "cfpb" / "tfidf-logreg" / baseline_source.name
    transformer = root / "data" / "evaluations" / "cfpb" / "transformer" / transformer_source.name
    baseline.parent.mkdir(parents=True)
    transformer.parent.mkdir(parents=True)
    baseline.write_bytes(baseline_source.read_bytes())
    transformer.write_bytes(transformer_source.read_bytes())
    return baseline, transformer


def _compare(root: Path, baseline: Path, transformer: Path):
    return compare_validation_models(
        baseline,
        transformer,
        repository_root=root,
        lineage_reader=lambda _: ("a" * 40, True),
        clock=lambda: datetime(2026, 7, 24, 12, tzinfo=UTC),
    )


def test_accepted_reports_produce_quality_only_proposal_and_replay(tmp_path: Path) -> None:
    baseline, transformer = _copy_accepted_reports(tmp_path)

    report = _compare(tmp_path, baseline, transformer)

    metrics = report["comparison"]["shared_validation_metrics"]
    assert metrics["macro_f1"]["delta_transformer_minus_baseline"] == pytest.approx(
        0.036085105687456376
    )
    assert metrics["worst_class_recall"]["delta_transformer_minus_baseline"] == pytest.approx(
        0.14977945814977972
    )
    assert all(metric["winner"] == "transformer" for metric in metrics.values())
    assert report["comparison"]["class_f1_wins"] == {
        "baseline": 1,
        "transformer": 10,
        "tie": 0,
    }
    assert report["utility_proposal"]["candidate_for_calibration"] == "transformer_minilm"
    assert report["utility_proposal"]["final_operational_model"] is None
    assert report["data"]["test_accessed"] is False
    assert report["claims"]["portfolio_promotion_approved"] is False

    replay = compare_validation_models(
        baseline,
        transformer,
        repository_root=tmp_path,
        lineage_reader=lambda _: ("b" * 40, False),
    )
    assert replay == report


def test_comparison_preserves_distinct_compute_scopes(tmp_path: Path) -> None:
    baseline, transformer = _copy_accepted_reports(tmp_path)

    report = _compare(tmp_path, baseline, transformer)

    assert report["models"]["baseline"]["compute_scope"] == "selected_candidate_fit_only"
    assert (
        report["models"]["transformer"]["compute_scope"]
        == "all_completed_training_and_validation_epochs"
    )
    assert "compute_ratio" not in json.dumps(report)
    assert report["comparison"]["non_comparable_evidence"]["calibration"] == "not_yet_measured"


def test_source_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    baseline, transformer = _copy_accepted_reports(tmp_path)
    changed = json.loads(transformer.read_text(encoding="utf-8"))
    changed["source"]["split_manifest_sha256"] = "f" * 64
    transformer.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(
        ValidationComparisonError, match="validation_comparison_source_identity_mismatch"
    ) as captured:
        _compare(tmp_path, baseline, transformer)

    assert captured.value.details == {"field": "split_identity"}


def test_transformer_proposal_requires_quality_dominance(tmp_path: Path) -> None:
    baseline, transformer = _copy_accepted_reports(tmp_path)
    changed = json.loads(baseline.read_text(encoding="utf-8"))
    selected_id = changed["selection"]["selected_candidate_id"]
    selected = next(
        candidate for candidate in changed["candidates"] if candidate["candidate_id"] == selected_id
    )
    selected["validation"]["accuracy"] = 0.99
    baseline.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(
        ValidationComparisonError,
        match="validation_comparison_quality_proposal_not_supported",
    ):
        _compare(tmp_path, baseline, transformer)


def test_changed_source_bytes_conflict_with_existing_report(tmp_path: Path) -> None:
    baseline, transformer = _copy_accepted_reports(tmp_path)
    _compare(tmp_path, baseline, transformer)
    changed = json.loads(transformer.read_text(encoding="utf-8"))
    changed["trained_at_utc"] = "2026-07-24T09:19:50Z"
    transformer.write_text(json.dumps(changed), encoding="utf-8")

    with pytest.raises(
        ValidationComparisonError, match="validation_comparison_report_identity_conflict"
    ):
        _compare(tmp_path, baseline, transformer)


def test_source_paths_are_confined_to_accepted_report_directories(tmp_path: Path) -> None:
    baseline, transformer = _copy_accepted_reports(tmp_path)
    unsafe_baseline = tmp_path / baseline.name
    unsafe_baseline.write_bytes(baseline.read_bytes())

    with pytest.raises(
        ValidationComparisonError,
        match="unsafe_validation_comparison_baseline_report_path",
    ):
        _compare(tmp_path, unsafe_baseline, transformer)


def test_dirty_or_uncommitted_lineage_is_rejected(tmp_path: Path) -> None:
    baseline, transformer = _copy_accepted_reports(tmp_path)

    with pytest.raises(
        ValidationComparisonError, match="validation_comparison_requires_clean_commit"
    ):
        compare_validation_models(
            baseline,
            transformer,
            repository_root=tmp_path,
            lineage_reader=lambda _: ("a" * 40, False),
        )


def test_safe_error_and_schema_exclude_source_values() -> None:
    result = safe_validation_comparison_error(
        ValidationComparisonError("validation_comparison_baseline_report_unreadable")
    )
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    encoded_evidence = json.dumps(
        {
            "data": schema["properties"]["data"],
            "comparison": schema["properties"]["comparison"],
        }
    )

    assert result["error"] == {"code": "validation_comparison_baseline_report_unreadable"}
    assert result["privacy"]["narratives_logged"] is False
    assert schema["properties"]["data"]["properties"]["test_accessed"] == {"const": False}
    assert "complaint_id" not in encoded_evidence
    assert "narrative_text" not in encoded_evidence
