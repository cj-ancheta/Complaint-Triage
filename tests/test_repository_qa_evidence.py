import hashlib
import json
import tomllib
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.real_extraction import PROJECT_ROOT

EVIDENCE_PATH = PROJECT_ROOT / "docs/qa/qa_evidence.json"
EVIDENCE_SCHEMA_PATH = PROJECT_ROOT / "contracts/repository-qa-evidence.schema.json"
FINDINGS_PATH = PROJECT_ROOT / "docs/qa/qa_findings.json"
FINDINGS_SCHEMA_PATH = PROJECT_ROOT / "contracts/repository-qa-findings.schema.json"
REPORT_PATH = PROJECT_ROOT / "docs/qa/repository_qa_report.md"
PLAN_PATH = PROJECT_ROOT / "docs/qa/repository_qa_plan.md"
BACKLOG_PATH = PROJECT_ROOT / "docs/qa/remediation_backlog.md"
AUDITED_COMMIT = "1b6130793d7b305605115dea255de15e89d2b94f"
LOCK_DIGESTS = {
    "bootstrap.lock.txt": "09c1fcb87431022971a755cbfc5d05886178d437b58e6918bf3aebd7ef4277a8",
    "lock-tool.lock.txt": "b0ff12ec9d12d217d0c6ff3a223cca4bf96785c08e1f66dc134b13c7e9ce1517",
    "standard-py313-linux-x86_64.lock.txt": (
        "645a371786d23314f640710c4e57feb0d702b07b0618fb23cbe742563ba3f436"
    ),
    "standard-py313-win-amd64.lock.txt": (
        "1574131bbb750886db5e473cba71ee0af824cce620c3e8fac7f7bb740e471c4b"
    ),
    "torch-cpu-py312-linux-x86_64.lock.txt": (
        "a4aaf0176db17457ea5769a9b4d7f15fed9d13505ac88e788a917885c447d3b3"
    ),
    "torch-cu130-py312-win-amd64.lock.txt": (
        "1bfd9fac6a6d412eb4ea0f0066ebdbd5f9256fa3ef4d53278a62786eddf5e14b"
    ),
    "transformer-py312-linux-x86_64.lock.txt": (
        "b3c05e97bbee2ed6308e042792414d8e7fe6efb3c97e7f376da440b1ab1614db"
    ),
    "transformer-py312-win-amd64.lock.txt": (
        "c56956af4e4ba583a9c1cbe49026734c81591e4606b267321c5ddf842fbff0fb"
    ),
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_errors(document_path: Path, schema_path: Path) -> list:
    document = _load_json(document_path)
    schema = _load_json(schema_path)
    return list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document))


def test_repository_qa_documents_validate_and_reconcile() -> None:
    assert _schema_errors(EVIDENCE_PATH, EVIDENCE_SCHEMA_PATH) == []
    assert _schema_errors(FINDINGS_PATH, FINDINGS_SCHEMA_PATH) == []

    evidence = _load_json(EVIDENCE_PATH)
    findings = _load_json(FINDINGS_PATH)
    assert evidence["audited_commit"] == AUDITED_COMMIT
    assert findings["audited_commit"] == AUDITED_COMMIT
    assert evidence["status"] == findings["status"] == "review"

    counts = Counter(item["severity"] for item in findings["findings"])
    expected = {
        "critical": counts["critical"],
        "high": counts["high"],
        "medium": counts["medium"],
        "low": counts["low"],
        "total": len(findings["findings"]),
    }
    assert findings["summary"] == expected
    assert evidence["finding_summary"] == expected
    assert expected == {"critical": 0, "high": 3, "medium": 7, "low": 3, "total": 13}


def test_qa_101_source_constraints_exclude_audited_vulnerable_tooling() -> None:
    configuration = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert configuration["build-system"]["requires"] == ["setuptools>=83,<84"]
    dev_dependencies = set(configuration["project"]["optional-dependencies"]["dev"])
    assert "setuptools>=83,<84" in dev_dependencies
    assert "pytest>=9.0.3,<10" in dev_dependencies
    assert all(not dependency.startswith("pytest>=8") for dependency in dev_dependencies)


def test_qa_102_lock_artifacts_preserve_reviewed_digests_and_source_boundaries() -> None:
    lock_directory = PROJECT_ROOT / "requirements" / "locks"
    contents: dict[str, str] = {}

    assert {path.name for path in lock_directory.glob("*.lock.txt")} == set(LOCK_DIGESTS)
    for filename, expected_digest in LOCK_DIGESTS.items():
        content = (lock_directory / filename).read_bytes()
        assert hashlib.sha256(content).hexdigest() == expected_digest
        contents[filename] = content.decode("utf-8")
        assert "--hash=sha256:" in contents[filename]

    for filename in (
        "standard-py313-linux-x86_64.lock.txt",
        "standard-py313-win-amd64.lock.txt",
    ):
        standard = contents[filename]
        assert "pytest==9.1.1" in standard
        assert "setuptools==83.0.0" in standard
        assert "transformers==" not in standard
        assert "torch==" not in standard

    for filename in (
        "transformer-py312-linux-x86_64.lock.txt",
        "transformer-py312-win-amd64.lock.txt",
    ):
        transformer = contents[filename]
        for requirement in (
            "jinja2==3.1.6",
            "networkx==3.6.1",
            "safetensors==0.8.0",
            "sympy==1.14.0",
            "tokenizers==0.22.2",
            "transformers==5.14.1",
        ):
            assert requirement in transformer
        assert "\ntorch==" not in transformer

    cuda = contents["torch-cu130-py312-win-amd64.lock.txt"]
    assert "--index-url https://download.pytorch.org/whl/cu130" in cuda
    assert "--only-binary :all:" in cuda
    assert "torch==2.13.0+cu130" in cuda
    assert "2efab1e83604ca628c6d85b9e188c153690980498d1297081a9dad704919303c" in cuda

    cpu = contents["torch-cpu-py312-linux-x86_64.lock.txt"]
    assert "--index-url https://download.pytorch.org/whl/cpu" in cpu
    assert "--only-binary :all:" in cpu
    assert "torch==2.13.0+cpu" in cpu
    assert "4ca4a9394b0c771238a4f73590fdbbc4debad85ed0fa63d026ae1b085da7d6e2" in cpu

    bootstrap = contents["bootstrap.lock.txt"]
    for requirement in ("pip==26.1.2", "setuptools==83.0.0", "wheel==0.47.0"):
        assert requirement in bootstrap
    assert "pip-tools==7.6.0" in contents["lock-tool.lock.txt"]


def test_qa_102_install_documentation_enforces_hashes_and_no_dependency_resolution() -> None:
    guide = (PROJECT_ROOT / "docs/reproducible_environments.md").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert guide.count("--require-hashes") >= 8
    assert "--require-hashes --no-deps" in guide
    assert "--no-deps --no-build-isolation -e ." in guide
    assert "standard-py313-win-amd64.lock.txt" in readme


def test_qa_103_ci_requires_offline_hash_locked_cpu_transformer_evidence() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    transformer_test = (PROJECT_ROOT / "tests/test_transformer_cpu_ci.py").read_text(
        encoding="utf-8"
    )

    for required in (
        "standard-py313-linux-x86_64.lock.txt",
        "transformer-py312-linux-x86_64.lock.txt",
        "torch-cpu-py312-linux-x86_64.lock.txt",
        'CT_REQUIRE_CPU_TRANSFORMER: "1"',
        'HF_HUB_OFFLINE: "1"',
        'TRANSFORMERS_OFFLINE: "1"',
        'python -m pytest -m "not gpu"',
        "--require-hashes --no-deps",
        "--no-deps --no-build-isolation -e .",
    ):
        assert required in workflow
    assert "data/raw" not in workflow
    assert "artifacts/" not in workflow
    assert "pytest.mark.cpu_transformer" in transformer_test
    assert "default_data_collator" in transformer_test
    assert "save_file" in transformer_test


def test_check_references_resolve_to_unique_findings() -> None:
    evidence = _load_json(EVIDENCE_PATH)
    findings = _load_json(FINDINGS_PATH)
    finding_ids = [item["finding_id"] for item in findings["findings"]]
    check_ids = [item["check_id"] for item in evidence["checks"]]

    assert len(finding_ids) == len(set(finding_ids))
    assert len(check_ids) == len(set(check_ids))
    statuses = {item["finding_id"]: item["status"] for item in findings["findings"]}
    assert statuses["QA-SEC-001"] == "resolved"
    assert statuses["QA-CI-001"] == "resolved"
    assert statuses["QA-REPRO-001"] == "resolved"
    assert all(
        status == "open"
        for finding_id, status in statuses.items()
        if finding_id not in {"QA-SEC-001", "QA-CI-001", "QA-REPRO-001"}
    )
    assert {item["finding_id"] for item in findings["findings"]} == {
        finding_id for check in evidence["checks"] for finding_id in check["finding_ids"]
    }


def test_qa_pack_preserves_privacy_and_release_boundaries() -> None:
    evidence = _load_json(EVIDENCE_PATH)

    assert evidence["privacy"] == {
        "contains_narratives": False,
        "contains_complaint_ids": False,
        "contains_row_values": False,
        "raw_data_read_as_bytes_only": True,
        "frozen_test_used_for_modeling": False,
    }
    assert evidence["release_boundary"] == {
        "status": "manual_review_only_research_evidence",
        "automated_routing_authorized": False,
        "frozen_test_access_authorized": False,
        "deployment_authorized": False,
        "public_metric_promotion_authorized": False,
        "paper_drafting_authorized": False,
    }


def test_human_readable_qa_documents_cover_every_finding_and_gate() -> None:
    findings = _load_json(FINDINGS_PATH)
    report = REPORT_PATH.read_text(encoding="utf-8")
    plan = PLAN_PATH.read_text(encoding="utf-8")
    backlog = BACKLOG_PATH.read_text(encoding="utf-8")

    for finding in findings["findings"]:
        assert finding["finding_id"] in report
        assert finding["finding_id"] in backlog

    for required in (
        "## Privacy-preserving evidence rules",
        "## Research handoff gate",
        "## Planned paper structure after QA acceptance",
    ):
        assert required in plan
    for required in (
        "## Executive conclusion",
        "## Independent ML-evidence recomputation",
        "## Evidence readiness matrix",
        "## Limitations of this audit",
    ):
        assert required in report
