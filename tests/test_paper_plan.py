import re

from complaint_triage.real_extraction import PROJECT_ROOT

PAPER_ROOT = PROJECT_ROOT / "paper"
CITATION_PATH = PROJECT_ROOT / "CITATION.cff"
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
READINESS_FILES = {
    "impact_statement.md",
    "prospective_causal_protocol.md",
    "publication_checklist.md",
    "publication_readiness.md",
}
SUBMISSION_FILES = {
    "README.md",
    "deposit_metadata.md",
    "pre_publish_verification.md",
    "submission_summary.md",
}


def _read(filename: str) -> str:
    return (PAPER_ROOT / filename).read_text(encoding="utf-8")


def test_paper_planning_package_is_complete_and_links_resolve() -> None:
    assert PAPER_FILES | LITERATURE_FILES | DRAFT_FILES | READINESS_FILES <= {
        path.name for path in PAPER_ROOT.glob("*.md")
    }

    readme = _read("README.md")
    local_links = re.findall(r"\[[^]]+\]\(([^)]+\.md)\)", readme)
    assert set(local_links) == (
        (PAPER_FILES | LITERATURE_FILES | DRAFT_FILES | READINESS_FILES) - {"README.md"}
    ) | {"generated/result_tables.md", "submission/README.md"}
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
        _read(filename)
        for filename in PAPER_FILES | LITERATURE_FILES | DRAFT_FILES | READINESS_FILES
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
    assert len(re.findall(r"^\d+\. ", research_questions, flags=re.MULTILINE)) == 5
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

    for research_question in ("RQ1", "RQ2", "RQ3", "RQ4", "RQ5"):
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
    assert "publication primary-source search complete" in questions.lower()


def test_manuscript_is_complete_cited_and_evidence_bounded() -> None:
    manuscript = _read("manuscript.md")
    references = _read("references.md")
    source_ids = set(re.findall(r"^### ([A-Z][A-Z0-9-]+)$", references, flags=re.MULTILINE))
    cited_ids = set(re.findall(r"\[([A-Z][A-Z0-9-]+)\]\(references\.md#", manuscript))

    assert 5_000 <= len(manuscript.split()) <= 8_500
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


def test_publication_readiness_preserves_release_authority_boundary() -> None:
    readiness = _read("publication_readiness.md")
    evidence = (PROJECT_ROOT / "docs" / "qa" / "qa_evidence.json").read_text(encoding="utf-8")

    assert "publication_ready_public_preprint_authorized" in readiness
    assert "public_metric_promotion_authorized: false" in readiness
    assert "| Editorial owner review" in readiness and "| pass |" in readiness
    assert "| Bounded public reporting" in readiness and "| pass |" in readiness
    normalized_readiness = re.sub(r"\s+", " ", readiness)
    assert "does not reinterpret the metrics as final performance" in normalized_readiness
    assert '"public_metric_promotion_authorized": false' in evidence
    assert '"frozen_test_access_authorized": false' in evidence
    assert '"deployment_authorized": false' in evidence


def test_manuscript_embeds_every_generated_figure_with_alt_text() -> None:
    manuscript = _read("manuscript.md")
    figure_links = re.findall(r"!\[([^]]+)]\((generated/f\d-[^)]+\.svg)\)", manuscript)

    assert len(figure_links) == 7
    assert len({path for _, path in figure_links}) == 7
    assert all(alt.strip() for alt, _ in figure_links)
    assert all((PAPER_ROOT / path).is_file() for _, path in figure_links)


def test_causal_protocol_is_actionable_but_never_presented_as_observed_evidence() -> None:
    manuscript = _read("manuscript.md")
    protocol = _read("prospective_causal_protocol.md")
    checklist = _read("publication_checklist.md")

    for required in (
        "design_blueprint_not_registered_not_conducted",
        "ATE_correct = E[Y(1) - Y(0)]",
        "ATE_time = E[T(1) - T(0)]",
        "intention-to-treat",
        "independent",
        "route-specific",
        "random assignment",
    ):
        assert required.lower() in protocol.lower()

    for prohibited in (
        "the causal study shows",
        "the trial demonstrated",
        "causally improved reviewer",
    ):
        assert prohibited not in manuscript.lower()
        assert prohibited not in protocol.lower()

    assert "present paper reports no causal effect" in manuscript
    assert "design_blueprint_not_registered_not_conducted" in checklist
    assert "causal estimate, trial completion" in checklist


def test_publication_citation_metadata_matches_the_released_manuscript() -> None:
    citation = CITATION_PATH.read_text(encoding="utf-8")
    manuscript = _read("manuscript.md")

    for required in (
        "cff-version: 1.2.0",
        "version: 1.0.1",
        "date-released: 2026-07-27",
        "family-names: Ancheta",
        "given-names: Charles Jr",
        "https://github.com/cj-ancheta/Complaint-Triage",
    ):
        assert required in citation
    assert "Decision Impact, Validation" in citation
    assert "Decision Impact, Validation" in manuscript
    assert "Version 1.0.1" in manuscript
    assert "TODO" not in citation


def test_submission_package_is_complete_and_preserves_release_boundaries() -> None:
    submission_root = PAPER_ROOT / "submission"
    assert SUBMISSION_FILES == {path.name for path in submission_root.glob("*.md")}
    package = "\n".join(
        (submission_root / filename).read_text(encoding="utf-8") for filename in SUBMISSION_FILES
    )
    lowered = re.sub(r"\s+", " ", package.lower())

    for required in (
        "package_ready_doi_not_minted",
        "publication / preprint",
        "all rights reserved",
        "validation-only",
        "manual-review-only",
        "design_blueprint_not_registered_not_conducted",
        "no causal effect",
        "paper-v1.0.1",
    ):
        assert required in lowered
    assert "10.5281/zenodo." not in lowered
    assert "the causal study shows" not in lowered
    assert "cc by" in lowered and "default cc by license has been removed" in lowered

    readme = (submission_root / "README.md").read_text(encoding="utf-8")
    links = re.findall(r"\[[^]]+]\(([^)]+\.md)\)", readme)
    assert set(links) == SUBMISSION_FILES - {"README.md"}
    assert all((submission_root / link).is_file() for link in links)


def test_impact_statement_leads_with_the_decision_and_preserves_causal_limits() -> None:
    impact = re.sub(r"\s+", " ", _read("impact_statement.md").lower())

    for required in (
        "no-go decision",
        "no suggestions for one required category",
        "manual review only",
        "cannot show that ai assistance",
        "prospective target-trial blueprint",
        "intention-to-treat",
        "route-specific safety constraints",
    ):
        assert required in impact
    assert "causally improves" not in impact


def test_all_paper_local_links_resolve() -> None:
    for document in PAPER_ROOT.glob("*.md"):
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^]]*]\(([^)]+)\)", text):
            if target.startswith(("https://", "http://", "mailto:")):
                continue
            path_text = target.split("#", maxsplit=1)[0]
            if not path_text:
                continue
            assert (document.parent / path_text).is_file(), f"broken link in {document}: {target}"
