import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from complaint_triage.majority_baseline import (
    MajorityBaselineError,
    evaluate_constant_predictor,
    evaluate_majority_baseline,
    safe_majority_baseline_error,
    select_training_majority,
)

REPOSITORY_ROOT = Path(__file__).parents[1]
REAL_SPLIT_MANIFEST = (
    REPOSITORY_ROOT
    / "data/manifests/cfpb/splits"
    / "cfpb-run-20260722T130728Z-2b7815d4c850-split-1.0.0.json"
)


def test_majority_is_selected_from_training_counts_only() -> None:
    counts = {
        "train": {"A": 6, "B": 4},
        "validation": {"A": 2, "B": 8},
        "test": {"A": 1, "B": 9},
    }

    predicted = select_training_majority(counts["train"])
    evaluation = evaluate_constant_predictor(counts, predicted, ("A", "B"))

    assert predicted == "A"
    assert evaluation["train"]["metrics"] == {
        "accuracy": 0.6,
        "macro_precision": 0.3,
        "macro_recall": 0.5,
        "macro_f1": 0.375,
        "weighted_f1": 0.45,
    }
    assert evaluation["validation"]["metrics"]["accuracy"] == 0.2
    assert evaluation["test"]["metrics"]["accuracy"] == 0.1
    assert evaluation["train"]["per_class"]["B"]["f1"] == 0.0
    assert evaluation["train"]["confusion_matrix"]["rows"] == [[6, 0], [4, 0]]


def test_training_majority_tie_fails_closed() -> None:
    with pytest.raises(MajorityBaselineError, match="majority_label_tie") as captured:
        select_training_majority({"A": 5, "B": 5})

    assert captured.value.details == {"tied_label_count": 2}


def test_safe_error_contains_no_row_values() -> None:
    report = safe_majority_baseline_error(MajorityBaselineError("majority_label_tie"))

    assert report["error"] == {"code": "majority_label_tie"}
    assert report["privacy"] == {
        "narratives_logged": False,
        "complaint_ids_logged": False,
        "row_values_in_report": False,
    }


def test_real_aggregate_fixture_writes_schema_valid_idempotent_report(tmp_path: Path) -> None:
    target = (
        tmp_path
        / "data/manifests/cfpb/splits"
        / "cfpb-run-20260722T130728Z-2b7815d4c850-split-1.0.0.json"
    )
    target.parent.mkdir(parents=True)
    target.write_bytes(REAL_SPLIT_MANIFEST.read_bytes())
    fixed_time = datetime(2026, 7, 23, 9, tzinfo=UTC)

    first = evaluate_majority_baseline(
        target,
        repository_root=tmp_path,
        lineage_reader=lambda _root: ("c" * 40, True),
        clock=lambda: fixed_time,
    )

    def unexpected_lineage_call(_root: Path) -> tuple[str, bool]:
        raise AssertionError("idempotent report must use stored lineage")

    second = evaluate_majority_baseline(
        target,
        repository_root=tmp_path,
        lineage_reader=unexpected_lineage_call,
    )

    assert first == second
    assert first["model"]["predicted_label"] == (
        "Credit reporting or other personal consumer reports"
    )
    assert first["model"]["selection_split"] == "train"
    assert first["evaluation"]["train"]["record_count"] == 394_564
    assert first["evaluation"]["validation"]["record_count"] == 80_992
    assert first["evaluation"]["test"]["record_count"] == 85_786
    assert all(first["checks"].values())
    assert first["claims"]["portfolio_promotion_approved"] is False
    output = (
        tmp_path
        / "data/evaluations/cfpb/majority"
        / "cfpb-run-20260722T130728Z-2b7815d4c850-majority-baseline-1.0.0.json"
    )
    assert json.loads(output.read_text()) == first
