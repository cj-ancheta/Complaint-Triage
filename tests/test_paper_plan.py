import re

from complaint_triage.real_extraction import PROJECT_ROOT

PAPER_ROOT = PROJECT_ROOT / "paper"
PAPER_FILES = {
    "README.md",
    "claim_rules.md",
    "evidence_inventory.md",
    "literature_questions.md",
    "outline.md",
    "table_figure_plan.md",
}
LITERATURE_FILES = {"claim_source_matrix.md", "references.md"}
DRAFT_FILES = {"manuscript.md"}


def _read(filename: str) -> str:
    return (PAPER_ROOT / filename).read_text(encoding="utf-8")


def test_paper_planning_package_is_complete_and_links_resolve() -> None:
    assert PAPER_FILES | LITERATURE_FILES | DRAFT_FILES <= {
        path.name for path in PAPER_ROOT.glob("*.md")
    }

    readme = _read("README.md")
    local_links = re.findall(r"\[[^]]+\]\(([^)]+\.md)\)", readme)
    assert set(local_links) == (PAPER_FILES | LITERATURE_FILES | DRAFT_FILES) - {"README.md"}
    assert all((PAPER_ROOT / link).is_file() for link in local_links)


def test_evidence_inventory_maps_every_core_aggregate_report() -> None:
    inventory = _read("evidence_inventory.md")
    evaluation_root = PROJECT_ROOT / "data" / "evaluations" / "cfpb"
    required_directories = {
        "majority",
        "tfidf-logreg",
        "transformer",
        "model-comparison",
        "error-analysis",
        "calibration",
        "model-selection",
        "abstention",
    }

    for directory in required_directories:
        reports = list((evaluation_root / directory).glob("*.json"))
        assert len(reports) == 1
        relative_report = reports[0].relative_to(PROJECT_ROOT).as_posix()
        assert relative_report in inventory


def test_claim_rules_preserve_validation_privacy_and_human_oversight_boundaries() -> None:
    rules = _read("claim_rules.md").lower()
    outline = _read("outline.md").lower()
    inventory = _read("evidence_inventory.md").lower()
    paper_text = "\n".join(
        _read(filename) for filename in PAPER_FILES | LITERATURE_FILES | DRAFT_FILES
    ).lower()

    for required_phrase in (
        "validation-only",
        "frozen-test",
        "demographic fairness",
        "manual review",
    ):
        assert required_phrase in rules

    assert "frozen-test access is not authorized" in inventory
    assert "human oversight" in outline
    assert "frozen_test_access_authorized = true" not in paper_text
    assert "deployment_authorized = true" not in paper_text


def test_outline_covers_research_questions_and_complete_paper_structure() -> None:
    readme = _read("README.md")
    outline = _read("outline.md")

    research_questions = readme.split("## Research questions", maxsplit=1)[1].split(
        "## Files", maxsplit=1
    )[0]
    assert len(re.findall(r"^\d+\. ", research_questions, flags=re.MULTILINE)) == 4
    for section in (
        "## 1. Title page and abstract",
        "## 2. Introduction",
        "## 3. Related work",
        "## 4. Data and governance",
        "## 5. Methods",
        "## 6. Results",
        "## 7. Discussion",
        "## 8. Threats to validity and limitations",
        "## 9. Ethics, privacy, and human oversight",
        "## 10. Conclusion",
        "## 11. Reproducibility and artifact statement",
        "## Appendices",
    ):
        assert section in outline

    for research_question in ("RQ1", "RQ2", "RQ3", "RQ4"):
        assert research_question in outline
    assert "Evidence inputs:" in outline
    assert "Literature needed:" in outline


def test_literature_matrix_uses_defined_sources_and_records_scope_limits() -> None:
    references = _read("references.md")
    matrix = _read("claim_source_matrix.md")
    questions = _read("literature_questions.md")

    source_ids = re.findall(r"^### ([A-Z][A-Z0-9-]+)$", references, flags=re.MULTILINE)
    assert len(source_ids) >= 20
    assert len(source_ids) == len(set(source_ids))
    assert all(source_id in matrix for source_id in source_ids)
    assert len(re.findall(r"^\| C\d{2} \|", matrix, flags=re.MULTILINE)) >= 20
    assert "scope caveat" in matrix.lower()
    assert "initial search is complete" in questions.lower()


def test_manuscript_is_complete_cited_and_evidence_bounded() -> None:
    manuscript = _read("manuscript.md")
    references = _read("references.md")
    source_ids = set(re.findall(r"^### ([A-Z][A-Z0-9-]+)$", references, flags=re.MULTILINE))
    cited_ids = set(re.findall(r"\[([A-Z][A-Z0-9-]+)\]\(references\.md#", manuscript))

    assert 5_000 <= len(manuscript.split()) <= 8_000
    assert cited_ids == source_ids
    for section in (
        "## Abstract",
        "## 1. Introduction",
        "## 2. Related work",
        "## 3. Data and governance",
        "## 4. Methods",
        "## 5. Results",
        "## 6. Discussion",
        "## 7. Threats to validity and limitations",
        "## 8. Ethics, privacy, and human oversight",
        "## 9. Reproducibility and artifact statement",
        "## 10. Conclusion",
        "## Declarations",
    ):
        assert section in manuscript

    for required in (
        "0.885853",
        "0.883692",
        "0.735746",
        "0.699661",
        "0.207048",
        "0.057269",
        "manual review only",
        "no frozen-test performance",
    ):
        assert required in manuscript

    lowered = manuscript.lower()
    assert "frozen_test_access_authorized = true" not in lowered
    assert "deployment_authorized = true" not in lowered
    assert "demographically fair" not in lowered
