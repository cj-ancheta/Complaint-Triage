from pathlib import Path

from complaint_triage.paper_tables import (
    MANIFEST_PATH,
    MANUSCRIPT_PATH,
    TABLES_PATH,
    generate_assets,
    generate_manuscript,
    render_abstention_table,
    render_calibration_table,
    render_cohort_table,
    render_manuscript,
    render_model_comparison_table,
    render_per_class_table,
    render_qa_table,
)


def test_generated_tables_match_committed_manuscript() -> None:
    assert generate_manuscript(check=True)
    assert generate_assets(check=True)
    assert TABLES_PATH.is_file()
    assert MANIFEST_PATH.is_file()


def test_generator_updates_stale_blocks_without_changing_other_prose(tmp_path: Path) -> None:
    manuscript = MANUSCRIPT_PATH.read_text(encoding="utf-8")
    stale = manuscript.replace("| Accuracy | 0.666881", "| Accuracy | STALE", 1)
    path = tmp_path / "manuscript.md"
    path.write_text(stale, encoding="utf-8")

    assert not generate_manuscript(path, check=True)
    assert not generate_manuscript(path)
    assert generate_manuscript(path, check=True)
    assert path.read_text(encoding="utf-8") == render_manuscript(manuscript)


def test_model_table_is_sourced_from_shared_validation_evidence() -> None:
    table = render_model_comparison_table()
    assert "| Accuracy | 0.666881 | 0.883692 | 0.885853 | +0.002161 |" in table
    assert "| Macro F1 | 0.072741 | 0.699661 | 0.735746 | +0.036085 |" in table
    assert "| Worst-class recall | 0.000000 | 0.057269 | 0.207048 | +0.149779 |" in table


def test_calibration_table_uses_october_before_after_results() -> None:
    table = render_calibration_table()
    assert "| Accuracy | 0.882121 | 0.882121 | +0.000000 |" in table
    assert "| Negative log likelihood | 0.371454 | 0.369804 | -0.001650 |" in table
    assert "| Equal-mass ECE, 15 bins | 0.023598 | 0.017946 | -0.005652 |" in table


def test_abstention_table_preserves_negative_gate_evidence() -> None:
    table = render_abstention_table()
    assert "| 0.75 | 0.856279 | 0.143721 | 0.936402 | 0.054457 |" in table
    assert "least-suggested class has 4 cases" in table
    assert "| 0.80 | 0.825440 | 0.174560 | 0.945032 | 0.045373 |" in table
    assert "least-suggested class has 0 cases" in table
    assert "predicted-class precision gate fails" in table


def test_generated_source_manifest_is_aggregate_only() -> None:
    manifest = MANIFEST_PATH.read_text(encoding="utf-8")
    assert '"contains_narratives": false' in manifest
    assert '"contains_complaint_ids": false' in manifest
    assert '"contains_row_values": false' in manifest
    assert manifest.count('"sha256":') == 7
    assert "data/raw" not in manifest
    assert "artifacts/" not in manifest


def test_remaining_planned_tables_are_generated_from_aggregate_sources() -> None:
    cohort = render_cohort_table()
    assert "| Structurally staged | 979,995 | input |" in cohort
    assert "| Canonical included | 561,342 | after duplicate isolation |" in cohort
    assert "| Frozen test | 85,786 | sealed; no paper performance |" in cohort

    per_class = render_per_class_table()
    assert per_class.count("\n|") == 12
    assert "| Debt or credit management | 227 | 0.106996 | 0.057269 |" in per_class
    assert (
        "| Mortgage | 2,036 | 0.876339 | 0.884086 | 0.873574 | 0.921415 | baseline |" in per_class
    )

    qa = render_qa_table()
    assert "| High | 3 |" in qa
    assert "| Medium | 7 |" in qa
    assert "| Low | 3 |" in qa
    assert "| security | 2 | resolved |" in qa
