# QA remediation backlog

Status: proposed for owner review  
Source: [repository QA report](repository_qa_report.md)

The order protects the accepted evidence before changing maintainability or
paper presentation. Each item is a separate bounded issue with a review
checkpoint. No item authorizes frozen-test access, training, deployment,
threshold changes, or metric promotion.

## Release gates

| Order | Issue | Findings | Proposed outcome | Verification | Paper gate |
|---:|---|---|---|---|---|
| 1 | QA-101 remediate vulnerable tooling — accepted | QA-SEC-001 | pytest and setuptools constraints/installations contain no known advisory found by the audit | clean `pip-audit`; 291+1-skip standard and 292-pass transformer suites | resolved |
| 2 | QA-102 lock both environments — accepted | QA-REPRO-001 | exact-digest locks plus deterministic update/rebuild instructions and isolated package-source boundaries | clean `--require-hashes` installs, `pip check`, and complete PostgreSQL-backed suites | resolved |
| 3 | QA-103 add transformer CI — accepted | QA-CI-001 | independent hash-locked Linux standard/CPU-transformer jobs; offline synthetic CPU evidence; GPU acceptance explicitly excluded | local replays and GitHub Actions run 30161131645 pass both jobs | resolved |
| 4 | QA-104 protect evidence workflow — accepted | QA-GIT-001 | protected `main` with strict required CI, PR delivery, admin enforcement, linear history, and no force-push/deletion | GitHub branch API reports every accepted control | resolved |
| 5 | QA-105 add security supply-chain gates — accepted | QA-SEC-002, QA-GOV-001 | redacted secret scan, strict dependency audit/update automation, privacy-bounded SBOM, container scan, Action SHA pins, security/ownership/reuse policy | run 30162536790 passes all three jobs; protected `main` requires them | resolved |
| 6 | QA-106 ratchet coverage — accepted | QA-TEST-001, QA-WARN-001 | focused subprocess error tests, unexpected-warning errors, independent 69% floors | run 30163081497 passes both profiles and security | resolved |
| 7 | QA-107 restore schema drift checks — accepted | QA-DB-001 | authoritative eight-table metadata and multi-schema Alembic gate | run 30163564539 passes empty upgrades and `alembic check` twice | resolved |
| 8 | QA-108 establish static typing | QA-TYPE-001 | scoped checker baseline and CI gate | configured checker passes protected scope | non-blocking |
| 9 | QA-109 automate retention checkpoint | QA-DATA-001 | local-only deadline guard/reminder and deletion runbook | safe time-bound tests; no raw values or uploads | blocking by 2026-11-19 |
| 10 | QA-110 harden artifact trust boundary | QA-SERIAL-001 | documented trusted-local boundary and safer resume serialization decision | malicious/untrusted path tests remain rejected | non-blocking |
| 11 | QA-111 split orchestration modules | QA-MAINT-001 | smaller handlers/pure functions with unchanged interfaces and reports | characterization tests and full suites pass | non-blocking |

## QA-101 acceptance notes

- Do not merely upgrade the local virtual environments; update source
  constraints so fresh CI installs are safe.
- Confirm compatibility between pytest 9.0.3, pytest-cov, plugins, Python 3.12,
  and Python 3.13.
- Upgrade the transformer environment's setuptools to at least 83.0.0.
- Record any unavoidable audit skip, especially the local editable project and
  CUDA-specific torch distribution.

## QA-102 acceptance notes

- Keep human-edited direct dependency intent in `pyproject.toml`.
- Generate platform-aware, hashed lock inputs for the standard CPU/CI stack and
  the isolated CUDA/transformer stack.
- Treat the CUDA wheel index and artifact hash as executable install policy,
  not a comment.
- Capture Python, OS/platform, CUDA, torch, transformers, tokenizer, NumPy,
  scikit-learn, SciPy, PostgreSQL, and Git commit identities in the replay
  record.

QA-102 satisfies the local Windows boundary with separate Python 3.13 standard,
Python 3.12 transformer, bootstrap, compiler-tool, and CUDA-wheel locks. The
repository contract pins their exact digests. QA-103 remains responsible for a
Linux-specific CI lock and remote replay; it must not reuse the Windows files.

## QA-103 acceptance notes

- The CI job must not download the 1.68 GB raw corpus or commit/use local model
  artifacts.
- Exercise transformer loading and computation with synthetic fixtures or
  deterministic test doubles; preserve offline Hugging Face settings.
- Separate true GPU acceptance from ordinary pull-request CI and document who
  can run it and what evidence it produces.

## QA-105 acceptance notes

- Secret scanning must redact matched values in logs.
- Dependency audit must fail on actionable vulnerabilities and document
  explicit, reviewed ignores with expiry.
- SBOM output must contain dependency metadata only, not paths or environment
  values that reveal user information.
- Pin third-party Actions to immutable commits and document the upstream tag.

QA-105 satisfies these controls with a full-history Gitleaks gate and ephemeral
negative fixture, target-Python hash-locked audit tooling, strict PyPI audits,
CycloneDX completion for the isolated non-PyPI CPU wheel, a hardened
digest-pinned PostgreSQL image, and individually justified Trivy exceptions
expiring 2026-08-15. GitHub Actions run 30162536790 passes `standard`,
`transformer-cpu`, and `security`; protected `main` requires all three. The
repository also tracks SECURITY.md, CODEOWNERS, weekly Dependabot configuration,
and an explicit all-rights-reserved LICENSE.

## QA-106 acceptance notes

Start with behaviorally important paths rather than chasing a cosmetic global
percentage:

1. artifact missing/hash mismatch/label mismatch;
2. subprocess timeout, non-zero exit, and malformed output;
3. transformer resume identity and corrupt state;
4. calibration/abstention schema and gate edge cases;
5. CLI dispatch and safe error payloads.

Set the first branch floor at or below the newly demonstrated value, then allow
only increases. Keep standard and transformer coverage reports separate so one
cannot hide the other's gaps.

QA-106 sets independent 69% floors after demonstrating 69.36% locally for the
standard profile and 69.02% remotely for the Linux CPU-transformer profile. The
local CUDA-transformer suite reaches 70.74%; its GPU path remains explicitly
outside ordinary CI. Focused tests raise `model_selection.py` from 49% to 53%
and cover offline execution, timeout, non-zero exit, and malformed output.
Unexpected warnings fail; the exact upstream joblib/NumPy warning is the sole
reviewed exception. Run 30163081497 passes all three jobs.

## Research-paper handoff checklist

- [ ] Owner accepts the QA finding inventory.
- [ ] QA-101, QA-102, and QA-103 are resolved or explicitly approved as paper
  limitations.
- [ ] QA evidence is rerun from a clean, identified commit.
- [ ] Machine-readable evidence and finding files validate and reconcile.
- [ ] The paper scope is validation-only and manual-review-only.
- [ ] No raw narratives, complaint IDs, frozen-test metrics, fairness claims,
  deployment claims, or public metric claims are introduced.
- [ ] Primary literature sources are collected with a claim-to-source matrix.
- [ ] Tables and figures are generated only from accepted aggregate evidence.
- [ ] Limitations include temporal generalizability, taxonomy choice, rare-class
  support, single-source data, calibration scope, and software-control gaps.
- [ ] Artifact availability describes what is public, what remains local, and
  why the raw data/model artifacts are excluded from Git.
