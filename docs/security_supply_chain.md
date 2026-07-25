# Security and software-supply-chain gates

Status: QA-105 implementation complete; remote required-check evidence pending

This guide defines the merge controls for secrets, Python dependencies,
software bills of materials (SBOMs), the PostgreSQL image, workflow actions,
and dependency updates. The controls protect repository and evidence integrity;
they do not authorize deployment, frozen-test access, or model automation.

## Required security job

The `security` job checks the complete Git history with Gitleaks 8.28.0. Output
is redacted. A controlled secret is assembled only inside an ephemeral runner
directory, and the job must observe the scanner's rejection exit code. The
literal fixture is never committed or printed.

The project-specific allowlist applies only to lines identifying the public
CFPB API source-contract commit. Those values are Git provenance, not
credentials. The default provider and entropy rules remain enabled, and a
separate project rule detects the controlled QA pattern.

## Dependency audit and SBOM

Both `standard` and `transformer-cpu` jobs install `pip-audit==2.10.1` from a
target-Python, Linux x86-64, hash-enforced tool lock. `pip-audit --local
--strict` fails the job for an actionable advisory or an unresolved
distribution. The editable project is reviewed Git source rather than a
package-index artifact, so it is installed only after this third-party audit.

Each job audits the hash-locked PyPI environment before installing the reviewed
editable project; this makes strict mode fail on every skipped or unresolved
PyPI distribution instead of treating the intentional editable source as an
audit error. The non-PyPI CPU Torch wheel is installed afterward from its
isolated hash lock: OSV cannot resolve its `+cpu` identity, so it is included in
the SBOM by a tested completion helper with its reviewed SHA-256, version, and
explicit audit-boundary property. It remains the advisory-database boundary
recorded by ADR 0017. The project source is protected by Git review, Ruff, and
tests.

Each job also generates a CycloneDX JSON SBOM from that third-party environment.
The workflow validates that the document contains dependency components and
does not contain the runner home path or the database-secret variable name.
SBOM files are ephemeral CI evidence and ignored locally; they contain package
metadata only and must never include raw data, narratives, model artifacts,
credentials, or user paths.

## Container boundary and reviewed exceptions

The database image is built from an immutable digest of PostgreSQL
18.4-alpine3.23 and immediately applies current Alpine security upgrades. Trivy
0.70.0 fails on fixed HIGH or CRITICAL operating-system vulnerabilities.

The initial upstream-image scan found fixed Alpine vulnerabilities and Go
standard-library findings embedded in the `gosu` UID-switch binary. Upgrading
the Alpine packages removed the actionable package findings. Fifteen remaining
`gosu` findings are individually path-scoped, justified, and expire on
2026-08-15. They are not blanket CVE ignores. Before expiry, rebuild against an
updated upstream image or `gosu`, rescan, and remove every obsolete exception.
An expired entry must not be renewed without a fresh reachability and impact
review.

## Immutable workflow dependencies

Every third-party GitHub Action is pinned to a reviewed 40-character commit:

- `actions/checkout` at its reviewed v4 commit;
- `actions/setup-python` at its reviewed v5 commit; and
- `aquasecurity/trivy-action` at its reviewed v0.36.0 commit.

The human-readable tag is retained as a comment; the commit controls execution.
Docker scanner images and the PostgreSQL base are also digest-pinned.

## Updates and ownership

Dependabot checks Python packages, GitHub Actions, and Docker weekly. A proposed
update still requires both runtime CI profiles plus the security job; it does
not bypass hash-lock regeneration or evidence review. `.github/CODEOWNERS`
names the repository owner. `LICENSE` explicitly preserves all rights while
allowing portfolio inspection, and `SECURITY.md` defines private reporting and
disclosure boundaries.

## Local verification

Run the repository contracts and the clean history scan before requesting
review:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_security_controls.py -q
docker run --rm -v "${PWD}:/repo:ro" `
  zricethezav/gitleaks:v8.28.0@sha256:cdbb7c955abce02001a9f6c9f602fb195b7fadc1e812065883f695d1eeaba854 `
  git /repo --config /repo/.gitleaks.toml --redact --no-banner
docker build --tag complaint-triage-postgres:qa105 docker/postgres
```

Run the Trivy command encoded in `.github/workflows/ci.yml` against that exact
image. Local success is implementation evidence only. QA-105 closes after a
pull request passes `standard`, `transformer-cpu`, and `security`, and branch
protection requires all three exact contexts.
