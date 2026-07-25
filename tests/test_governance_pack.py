import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.real_extraction import PROJECT_ROOT

EVIDENCE_PATH = PROJECT_ROOT / "docs/governance_evidence.json"
SCHEMA_PATH = PROJECT_ROOT / "contracts/cfpb-governance-evidence.schema.json"
REQUIRED_DOCUMENT_SECTIONS = {
    "docs/problem_statement.md": ("## Decision being supported", "## Current evidence status"),
    "docs/data_sheet.md": ("## Source and collection context", "## Retention and deletion"),
    "docs/model_card.md": ("## Intended uses", "## Evaluation evidence", "## Release status"),
    "docs/risk_register.md": ("## Rating method", "## Risk register"),
    "docs/human_oversight.md": ("## Review triggers", "## Responsibility boundaries"),
    "docs/change_management.md": ("## Promotion checklist", "## Rollback"),
    "docs/security.md": ("## Threat model", "## Current control status"),
    "docs/governance_pack.md": ("## Release decision", "## Evidence lineage"),
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_governance_evidence_is_closed_and_all_hashes_reconcile() -> None:
    evidence = _load_json(EVIDENCE_PATH)
    schema = _load_json(SCHEMA_PATH)

    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(evidence)
    )
    assert errors == []
    assert set(evidence["documents"]) == set(REQUIRED_DOCUMENT_SECTIONS)
    assert len({item["name"] for item in evidence["evidence"]}) == 9

    for item in evidence["evidence"]:
        path = (PROJECT_ROOT / item["path"]).resolve()
        assert any(
            path.is_relative_to(PROJECT_ROOT / allowed)
            for allowed in ("data/evaluations/cfpb", "data/manifests/cfpb")
        )
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_required_governance_documents_have_review_sections() -> None:
    for relative_path, headings in REQUIRED_DOCUMENT_SECTIONS.items():
        path = (PROJECT_ROOT / relative_path).resolve()
        path.relative_to((PROJECT_ROOT / "docs").resolve())
        text = path.read_text(encoding="utf-8")
        for heading in headings:
            assert heading in text


def test_release_boundary_stays_closed() -> None:
    evidence = _load_json(EVIDENCE_PATH)
    decision = evidence["release_decision"]

    assert evidence["review"] == {
        "status": "accepted",
        "owner": "Charles Jr Ancheta",
        "accepted_on": "2026-07-25",
        "scope": "ct403_governance_pack_and_manual_review_only_release_decision",
    }
    assert decision == {
        "status": "manual_review_only_research_evidence",
        "reason": "no_candidate_threshold_passed_every_adr_0016_gate",
        "operational_threshold": None,
        "automated_routing_authorized": False,
        "frozen_test_access_authorized": False,
        "deployment_authorized": False,
        "public_metric_promotion_authorized": False,
    }
    assert evidence["privacy"] == {
        "contains_narratives": False,
        "contains_complaint_ids": False,
        "contains_row_values": False,
        "raw_data_git_tracking_allowed": False,
        "governance_pack_git_tracking_allowed": True,
    }


def test_ct_402_is_closed_without_implying_frozen_test_evaluation() -> None:
    backlog = (PROJECT_ROOT / "BACKLOG.md").read_text(encoding="utf-8")
    adr = (
        PROJECT_ROOT / "docs/decisions/0016-proposed-abstention-and-final-evaluation-policy.md"
    ).read_text(encoding="utf-8")
    model_card = (PROJECT_ROOT / "docs/model_card.md").read_text(encoding="utf-8")
    governance_pack = (PROJECT_ROOT / "docs/governance_pack.md").read_text(encoding="utf-8")

    assert "| CT-402 |" in backlog
    assert "| not applicable |" in backlog
    assert "frozen test partition remains untouched" in backlog
    assert "## CT-402 final disposition" in adr
    for document in (adr, model_card, governance_pack):
        assert "frozen test remains sealed" in document
    for document in (backlog, adr, model_card, governance_pack):
        assert "CT-402 is blocked" not in document
