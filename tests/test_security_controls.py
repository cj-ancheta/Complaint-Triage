import hashlib
import re

import pytest

from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.supply_chain import TORCH_CPU_SHA256, complete_transformer_sbom


def test_all_workflow_actions_are_immutable_and_security_gates_are_present() -> None:
    workflow = (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    actions = re.findall(r"^\s*uses:\s*([^@\s]+)@([^\s#]+)", workflow, flags=re.MULTILINE)

    assert actions
    assert all(re.fullmatch(r"[0-9a-f]{40}", revision) for _, revision in actions)
    assert set(actions) == {
        ("actions/checkout", "11d5960a326750d5838078e36cf38b85af677262"),
        ("actions/setup-python", "a26af69be951a213d495a4c3e4e4022e16d87065"),
        ("aquasecurity/trivy-action", "ed142fd0673e97e23eac54620cfb913e5ce36c25"),
    }
    for required in (
        "security:",
        "--redact",
        "scanner_status",
        "pip_audit --local --strict",
        "--format cyclonedx-json",
        "POSTGRES_PASSWORD' not in raw",
        "severity: HIGH,CRITICAL",
        "trivyignores: .trivyignore.yaml",
    ):
        assert required in workflow
    controlled_fixture = "CT_QA_SECRET_" + "7M4K9P2Q8R5T1V6W3X0Y7Z4A9B2C8D5E"
    assert controlled_fixture not in workflow


def test_security_inputs_are_pinned_reviewable_and_time_bounded() -> None:
    dockerfile = (PROJECT_ROOT / "docker/postgres/Dockerfile").read_text(encoding="utf-8")
    ignores = (PROJECT_ROOT / ".trivyignore.yaml").read_text(encoding="utf-8")
    gitleaks = (PROJECT_ROOT / ".gitleaks.toml").read_text(encoding="utf-8")
    dependabot = (PROJECT_ROOT / ".github/dependabot.yml").read_text(encoding="utf-8")

    assert (
        "postgres:18.4-alpine3.23@sha256:"
        "996d0920e4ff9df1fc19dacb904492f3c1ec0ec1cc338f0ad7123be7731c5f5e"
    ) in dockerfile
    assert "RUN apk upgrade --no-cache" in dockerfile
    assert ignores.count("expired_at: 2026-08-15") == 15
    assert ignores.count("statement:") == 15
    assert 'paths: ["usr/local/bin/gosu"]' in ignores
    assert "useDefault = true" in gitleaks
    assert "Public source-contract commit SHAs are provenance, not credentials" in gitleaks
    assert 'regexTarget = "line"' in gitleaks
    assert "CT_QA_SECRET_[A-Z0-9]{32}" in gitleaks
    assert set(re.findall(r"package-ecosystem:\s*([^\s]+)", dependabot)) == {
        "pip",
        "github-actions",
        "docker",
    }


def test_audit_tool_locks_and_security_policy_are_closed() -> None:
    expected = {
        "audit-tool-py312-linux-x86_64.lock.txt": (
            "5ae084ee14392bf862a5e37cd8a208ec9f52fb55a52bfe7a707be008b66e5c09"
        ),
        "audit-tool-py313-linux-x86_64.lock.txt": (
            "8d4f9edd15651b7996514c82358af7714843cf1b13fcd8b7a720b5ab7d638bac"
        ),
    }
    for filename, digest in expected.items():
        content = (
            (PROJECT_ROOT / "requirements/locks" / filename).read_bytes().replace(b"\r\n", b"\n")
        )
        assert hashlib.sha256(content).hexdigest() == digest
        assert b"pip-audit==2.10.1" in content
        assert b"--hash=sha256:" in content

    policy = (PROJECT_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    for heading in ("## Supported scope", "## Report a vulnerability", "## Disclosure"):
        assert heading in policy

    codeowners = (PROJECT_ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
    license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
    supply_chain = (PROJECT_ROOT / "docs/security_supply_chain.md").read_text(encoding="utf-8")
    assert "* @cj-ancheta" in codeowners
    assert "All rights reserved" in license_text
    assert "No permission is granted" in license_text
    assert "2026-08-15" in supply_chain
    assert "standard`, `transformer-cpu`, and `security`" in supply_chain


def test_non_pypi_torch_is_completed_in_the_transformer_sbom() -> None:
    payload = {"bomFormat": "CycloneDX", "components": []}

    completed = complete_transformer_sbom(payload, "2.13.0+cpu")

    torch_component = completed["components"][0]
    assert torch_component["name"] == "torch"
    assert torch_component["version"] == "2.13.0+cpu"
    assert torch_component["hashes"] == [{"alg": "SHA-256", "content": TORCH_CPU_SHA256}]
    assert "non-PyPI" in torch_component["properties"][0]["value"]


def test_transformer_sbom_rejects_an_unreviewed_torch_identity() -> None:
    with pytest.raises(ValueError, match="does not match the reviewed lock"):
        complete_transformer_sbom({"bomFormat": "CycloneDX", "components": []}, "2.13.1+cpu")
