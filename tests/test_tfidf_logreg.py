from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import pytest

from complaint_triage import tfidf_logreg
from complaint_triage.taxonomy import CURRENT_PRODUCT_LABELS
from complaint_triage.tfidf_logreg import (
    CANDIDATES,
    CandidateSpec,
    ModelingData,
    TfidfLogregError,
    build_estimator,
    build_vectorizer,
    fit_candidate_search,
    safe_tfidf_logreg_error,
    select_candidate,
    train_tfidf_logreg,
)


def _candidate(
    candidate_id: str,
    c: float,
    *,
    converged: bool = True,
    macro_f1: float = 0.5,
    worst_recall: float = 0.4,
    weighted_f1: float = 0.6,
) -> dict[str, object]:
    return {
        "spec": CandidateSpec(candidate_id, c, None),
        "converged": converged,
        "metrics": {
            "macro_f1": macro_f1,
            "worst_class_recall": worst_recall,
            "weighted_f1": weighted_f1,
        },
    }


def _synthetic_data() -> tuple[ModelingData, tuple[str, ...]]:
    labels = tuple(sorted(CURRENT_PRODUCT_LABELS))
    train_texts: list[str] = []
    train_labels: list[str] = []
    validation_texts: list[str] = []
    validation_labels: list[str] = []
    for index, label in enumerate(labels):
        token = f"classmarker{index}"
        for repetition in range(6):
            train_texts.append(f"common complaint {token} account issue repeat{repetition}")
            train_labels.append(label)
        validation_texts.append(f"validationonlytoken common complaint {token} account issue")
        validation_labels.append(label)
    return ModelingData(train_texts, train_labels, validation_texts, validation_labels), labels


def test_fixed_vectorizer_and_candidate_grid_match_approved_rule() -> None:
    vectorizer = build_vectorizer()

    assert vectorizer.ngram_range == (1, 2)
    assert vectorizer.min_df == 5
    assert vectorizer.max_df == 0.995
    assert vectorizer.max_features == 200_000
    assert vectorizer.sublinear_tf is True
    assert vectorizer.norm == "l2"
    assert str(vectorizer.dtype) == "<class 'numpy.float64'>"
    assert [(item.candidate_id, item.c, item.class_weight) for item in CANDIDATES] == [
        ("c0p5-unweighted", 0.5, None),
        ("c1p0-unweighted", 1.0, None),
        ("c0p5-balanced", 0.5, "balanced"),
        ("c1p0-balanced", 1.0, "balanced"),
    ]
    estimator = build_estimator(CANDIDATES[0])
    assert estimator.solver == "saga"
    assert estimator.penalty == "l2"
    assert estimator.random_state == 42
    assert estimator.max_iter == 200
    assert estimator.tol == 1e-3


def test_selection_excludes_nonconverged_before_comparing_metrics() -> None:
    selected = select_candidate(
        [
            _candidate("nonconverged", 0.5, converged=False, macro_f1=0.99),
            _candidate("eligible", 1.0, macro_f1=0.5),
        ]
    )

    assert selected["spec"].candidate_id == "eligible"


@pytest.mark.parametrize(
    ("left", "right", "winner"),
    [
        (
            _candidate("left", 1.0, macro_f1=0.6, worst_recall=0.1),
            _candidate("right", 0.5, macro_f1=0.5, worst_recall=0.9),
            "left",
        ),
        (
            _candidate("left", 1.0, worst_recall=0.5, weighted_f1=0.1),
            _candidate("right", 0.5, worst_recall=0.4, weighted_f1=0.9),
            "left",
        ),
        (
            _candidate("left", 1.0, weighted_f1=0.7),
            _candidate("right", 0.5, weighted_f1=0.6),
            "left",
        ),
        (_candidate("left", 0.5), _candidate("right", 1.0), "left"),
        (_candidate("a-stable", 0.5), _candidate("z-stable", 0.5), "a-stable"),
    ],
)
def test_selection_applies_each_ordered_tie_break(
    left: dict[str, object], right: dict[str, object], winner: str
) -> None:
    assert select_candidate([right, left])["spec"].candidate_id == winner


def test_selection_fails_closed_when_no_candidate_converges() -> None:
    with pytest.raises(TfidfLogregError, match="tfidf_no_converged_candidate"):
        select_candidate([_candidate("only", 0.5, converged=False)])


def test_synthetic_search_fits_vocabulary_on_train_only() -> None:
    data, labels = _synthetic_data()

    result = fit_candidate_search(data, labels=labels)

    assert len(result["candidates"]) == 4
    assert result["selected"]["spec"] in CANDIDATES
    vocabulary = result["selected"]["pipeline"].named_steps["tfidf"].vocabulary_
    assert "validationonlytoken" not in vocabulary
    assert result["feature_count"] <= 200_000
    assert result["validation_matrix_nnz"] > 0
    assert all(
        set(candidate["metrics"]["per_class"]) == set(labels) for candidate in result["candidates"]
    )


def test_modeling_search_requires_every_class_in_both_splits() -> None:
    data, labels = _synthetic_data()
    incomplete = ModelingData(
        data.train_texts,
        data.train_labels,
        data.validation_texts[1:],
        data.validation_labels[1:],
    )

    with pytest.raises(TfidfLogregError, match="tfidf_modeling_taxonomy_incomplete"):
        fit_candidate_search(incomplete, labels=labels)


def test_safe_error_contains_no_source_values() -> None:
    output = safe_tfidf_logreg_error(
        TfidfLogregError("tfidf_source_counts_do_not_reconcile", split="validation")
    )

    assert output["error"] == {
        "code": "tfidf_source_counts_do_not_reconcile",
        "split": "validation",
    }
    assert output["privacy"] == {
        "narratives_logged": False,
        "complaint_ids_logged": False,
        "row_values_in_report": False,
        "vocabulary_logged": False,
    }


def test_schema_and_source_never_publish_vocabulary_or_test_query() -> None:
    root = Path(__file__).parents[1]
    schema = json.loads(
        (root / "contracts" / "cfpb-tfidf-logreg-report.schema.json").read_text(encoding="utf-8")
    )
    source = (root / "src" / "complaint_triage" / "tfidf_logreg.py").read_text(encoding="utf-8")

    assert schema["properties"]["privacy"]["properties"]["contains_vocabulary"] == {"const": False}
    assert "o.split_assignment = ANY(%s)" in source
    assert '["train", "validation"]' in source
    assert "['train', 'validation']" not in source
    assert "o.split_assignment = 'test'" not in source


def test_full_synthetic_run_writes_closed_report_and_hashed_local_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = Path(__file__).parents[1]
    source_manifest = next((source_root / "data" / "manifests" / "cfpb" / "splits").glob("*.json"))
    destination = tmp_path / "data" / "manifests" / "cfpb" / "splits" / source_manifest.name
    destination.parent.mkdir(parents=True)
    destination.write_bytes(source_manifest.read_bytes())
    data, _ = _synthetic_data()
    load_calls = 0

    def load_synthetic(manifest, settings, *, smoke):
        nonlocal load_calls
        load_calls += 1
        assert smoke is False
        return data

    monkeypatch.setattr(tfidf_logreg, "load_modeling_data", load_synthetic)
    monkeypatch.setattr(tfidf_logreg, "_reconcile_data", lambda data, manifest: None)

    report = train_tfidf_logreg(
        destination,
        repository_root=tmp_path,
        settings=object(),
        lineage_reader=lambda root: ("a" * 40, True),
        clock=lambda: datetime(2026, 7, 23, 12, tzinfo=UTC),
    )

    artifact_path = tmp_path / report["artifact"]["relative_path"]
    assert artifact_path.is_file()
    assert artifact_path.stat().st_size == report["artifact"]["byte_count"]
    pipeline = joblib.load(artifact_path)
    assert len(pipeline.predict([data.validation_texts[0]])) == 1
    encoded_report = json.dumps(report)
    assert "validationonlytoken" not in encoded_report
    assert report["data"]["test_accessed"] is False
    assert report["claims"]["portfolio_promotion_approved"] is False
    assert report["privacy"]["contains_vocabulary"] is False

    replay = train_tfidf_logreg(
        destination,
        repository_root=tmp_path,
        settings=object(),
        lineage_reader=lambda root: ("b" * 40, False),
    )
    assert replay == report
    assert load_calls == 1
