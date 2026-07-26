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


def _read(filename: str) -> str:
    return (PAPER_ROOT / filename).read_text(encoding="utf-8")


def test_paper_planning_package_is_complete_and_links_resolve() -> None:
    assert {path.name for path in PAPER_ROOT.glob("*.md")} == PAPER_FILES

    readme = _read("README.md")
    local_links = re.findall(r"\[[^]]+\]\(([^)]+\.md)\)", readme)
    assert set(local_links) == PAPER_FILES - {"README.md"}
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
    paper_text = "\n".join(_read(filename) for filename in PAPER_FILES).lower()

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
