# Repository-wide QA report

Status: draft for owner review  
Audit date: 2026-07-25  
Audited commit: `1b6130793d7b305605115dea255de15e89d2b94f`  
Release boundary: unchanged; manual review only

## Executive conclusion

The repository's core evidence is internally consistent. No critical finding
was observed: Git is structurally sound, no raw data or governed binaries are
tracked, the sanitized current/history scan found no high-confidence secrets,
both complete test environments pass, PostgreSQL aggregate identities agree,
all referenced raw shards and governed local artifacts match their recorded
hashes, and 119 independently implemented ML-evidence checks all reproduce.

The repository is not yet a sufficiently controlled paper artifact without an
explicit remediation decision. The audit opened three high findings affecting
supply-chain safety, selected-model CI coverage, and fresh-environment
reproducibility. QA-101 has now technically resolved the supply-chain finding;
QA-102 resolved fresh-environment reproducibility, and QA-103 resolved the
selected-model CI gap. No high findings remain open. QA-104 also resolves branch
protection, leaving six medium and three low findings concerning coverage
enforcement, schema-drift detection, automated security controls, static typing,
maintainability, retention operations, trusted local serialization, warnings,
and repository governance metadata. All resolved findings are owner-accepted.

Finding totals:

| Critical | High | Medium | Low | Total |
|---:|---:|---:|---:|---:|
| 0 | 3 | 7 | 3 | 13 |

These are severity totals for the original audit inventory. Current disposition
is 4 resolved and 9 open; resolving a finding preserves its original severity
and evidence rather than deleting it.

The frozen test partition remains untouched for modeling or threshold
selection. No deployment, automated routing, threshold change, or public metric
promotion is authorized by this audit.

## Strong controls that passed

### Repository and privacy

- `git fsck --full --no-progress` completed without errors.
- The audit started from a clean worktree at commit `1b613079...` with 176
  tracked files and 49 commits.
- `.env`, `data/raw`, `artifacts`, `data/model_cache`, and `mlruns` remain
  untracked/ignored; no tracked file is at least 1 MiB.
- Six high-confidence credential patterns found zero matches in 176 current
  tracked files and 398 historical text blobs. The scanner emitted categories
  and locations only, never matched values.
- The raw corpus remained local and ignored: 16/16 shards reconciled by byte
  count and SHA-256, totalling 1,680,504,862 bytes.
- The TF-IDF artifact, MiniLM safetensors artifact, and scalar calibrator all
  exist locally and match their recorded byte counts and SHA-256 hashes.

### Code, schemas, documentation, and package entry points

- Ruff lint and format checks passed for the repository.
- `compileall` passed for `src` and `tests`.
- All 14 existing JSON Schemas passed Draft 2020-12 schema validation.
- All 51 Markdown files had valid local relative links at audit time.
- `pip check` passed in both the Python 3.13 standard environment and isolated
  Python 3.12 transformer environment.
- Both `python -m complaint_triage --help` and the installed
  `complaint-triage --help` entry point exited successfully.
- The transformer stack (`torch`, `transformers`, `tokenizers`, `safetensors`,
  and the project package) imports successfully in its isolated environment.

### Tests and database

- Standard environment plus disposable PostgreSQL: 291 passed, 1 skipped. The
  skip is the torch-dependent transformer-fit test, which is not applicable in
  the standard environment. Branch coverage was 69%.
- Transformer environment plus disposable PostgreSQL: 292 passed, 0 skipped.
  Branch coverage was 71%.
- Six PostgreSQL integration-test groups ran against randomly named disposable
  databases, exercised migrations, and force-dropped their databases.
- Alembic has one head, `0004_temporal_split`; the local database is at that
  revision.
- Aggregate database reconciliation passed: 979,995 raw, 979,995 staging,
  979,995 population outcomes, 979,194 split outcomes, 561,342 included,
  80,992 validation-included, and 85,786 test-included records.
- Included fingerprint duplicates were zero and 16 append-only triggers were
  present.

### Independent ML-evidence recomputation

An audit implementation that did not import the production metric helpers
recomputed split sums, confusion-matrix metrics, comparison deltas,
calibration-to-abstention lineage, 11 threshold count identities, coverage,
accepted accuracy/error rates, confusion sums, gate results, and final
eligibility. All 119 checks passed; no threshold was eligible.

Reproduced validation evidence:

| Candidate | Records | Accuracy | Macro F1 | Weighted F1 | Worst-class recall |
|---|---:|---:|---:|---:|---:|
| TF-IDF logistic regression | 80,992 | 0.883692 | 0.699661 | 0.879291 | 0.057269 |
| Compact MiniLM | 80,992 | 0.885853 | 0.735746 | 0.886692 | 0.207048 |

These are internal validation values, not frozen-test, production, or approved
public portfolio metrics.

## Findings

### High

#### QA-SEC-001 — Known vulnerabilities in required development/build tooling

- Status: resolved and accepted under QA-101
- Confidence: high
- Observed: `pip-audit 2.10.1` found `pytest 8.4.2` affected by
  `GHSA-6w46-j5rx-g56g` in both environments. The project currently requires
  `pytest>=8.3,<9`, which excludes the patched `9.0.3`. The transformer
  environment also has `setuptools 78.1.0`, affected by
  `GHSA-5rjg-fvgr-3xxf` and `GHSA-h35f-9h28-mq5c`; complete remediation requires
  `setuptools>=83.0.0`.
- Context: the pytest advisory concerns Unix shared temporary-directory
  handling, so the local Windows run is not directly exposed; CI runs on
  Ubuntu. The older setuptools path-traversal advisory can affect package-index
  downloads. The Unicode sdist advisory is macOS-specific, but the same old
  version carries both advisories.
- Impact: a fresh CI or contributor environment necessarily installs a known
  vulnerable pytest range, and the transformer build environment contains
  vulnerable packaging code.
- Required remediation: validate pytest 9.0.3 compatibility, change the dev
  constraint, require a current setuptools build tool, recreate both
  environments, rerun both full suites, and make dependency audit a CI gate.
- Verification: both environment audits exit zero, with only the local editable
  project and the non-PyPI CUDA torch wheel explicitly documented as unaudited.
- Resolution evidence: the source now requires `pytest>=9.0.3,<10` and
  `setuptools>=83,<84`. Both Python 3.13 and Python 3.12 environments resolved to
  pytest 9.1.1 and setuptools 83.0.0. `pip-audit 2.10.1` exited zero in both
  environments, the standard PostgreSQL-backed suite passed 291 tests with one
  expected torch-only skip, and the transformer suite passed all 292 tests.

Advisory sources: [pytest advisory](https://github.com/advisories/GHSA-6w46-j5rx-g56g),
[setuptools path-traversal advisory](https://github.com/advisories/GHSA-5rjg-fvgr-3xxf),
and [setuptools sdist advisory](https://github.com/advisories/GHSA-h35f-9h28-mq5c).

#### QA-CI-001 — CI does not exercise the selected transformer path

- Status: resolved and accepted under QA-103
- Confidence: high
- Observed: CI uses Python 3.13 and installs only `.[dev]`; it does not install
  the isolated Python 3.12 transformer stack. The local transformer suite is the
  only place all 291 tests run. Transformer orchestration branch coverage is
  only 41% in `transformer_fit.py` and 35% in `transformer_training.py`.
- Impact: the selected model's loading, calibration, fitting, and environment
  compatibility can regress while the required GitHub check remains green.
- Required remediation: add a bounded Python 3.12 CPU transformer CI job with
  pinned dependencies and cache/offline controls, separating GPU-only tests
  behind an explicit marker.
- Verification: CI runs the applicable transformer tests and publishes its
  coverage independently of the standard job.
- Remediation evidence: the workflow now defines independent hash-locked Python
  3.13 standard and Python 3.12 CPU-transformer jobs with separate coverage
  reports. The transformer job is offline, uses a single isolated official CPU
  Torch wheel, performs deterministic synthetic computation and safetensors
  round-trip evidence, and explicitly deselects the marked GPU acceptance test.
  Fresh target-platform containers passed `pip check`, the 293-test standard
  suite, and the 294-test CPU-transformer suite while governed local paths were
  unavailable. Both Linux PyPI manifests passed target-platform vulnerability
  audit. GitHub Actions run `30161131645` then passed both jobs on commit
  `3c37677e08711697de6a89fde5b59231fef377b3`.

#### QA-REPRO-001 — Fresh-environment dependencies are not fully locked

- Status: resolved and accepted under QA-102
- Confidence: high
- Observed: standard dependencies are bounded ranges without a lock file or
  hashes. Tokenizer dependencies use exact versions but no hashes. The CUDA
  torch file records one wheel hash in a comment but pip is not instructed to
  require it. CI installs from the ranges on every run.
- Impact: a future install can resolve to different transitive dependencies
  than the accepted validation run, reducing computational reproducibility and
  making failures time-dependent.
- Required remediation: generate reviewed Python 3.13 standard and Python 3.12
  transformer lock files with hashes; preserve the direct dependency policy in
  `pyproject.toml`; add deterministic lock verification/update instructions.
- Verification: clean environments install with `--require-hashes`, record the
  resolved manifest, and pass the full suites and aggregate evidence replay.
- Resolution evidence: five platform-specific artifacts now lock the installer
  bootstrap, lock compiler, Python 3.13 standard stack, Python 3.12 transformer
  stack, and isolated CUDA wheel with enforced hashes. Clean standard and
  transformer environments installed the third-party locks and then the local
  Git source with dependency resolution/build isolation disabled. Both passed
  `pip check` and the complete PostgreSQL-backed suite. The transformer replay
  imported exactly Torch `2.13.0+cu130`, Transformers `5.14.1`, Tokenizers
  `0.22.2`, and Safetensors `0.8.0`. A repository contract pins all five lock
  digests and proves Torch cannot leak into the PyPI-resolved lock.
- Scope limitation: these artifacts prove Windows AMD64 reproducibility for the
  two supported Python versions. QA-103 must create and verify a separate Linux
  lock for remote CI; the Windows locks are not represented as portable.

### Medium

#### QA-TEST-001 — Coverage gaps are measured but not enforced

- Confidence: high
- Observed: full branch coverage is 71%, with `model_selection.py` at 49%,
  `transformer_fit.py` at 41%, `transformer_training.py` at 35%, and
  `abstention_analysis.py` at 63%. CI has no `fail_under` threshold.
- Impact: critical orchestration and error branches can lose coverage without a
  failed check.
- Remediation: add focused unit/subprocess/artifact-failure tests and introduce
  a ratcheting coverage floor that cannot decrease.

#### QA-DB-001 — Alembic cannot detect model-to-migration drift

- Confidence: high
- Observed: `alembic check` reports that the migration environment provides no
  SQLAlchemy `MetaData`. Upgrade/current integration tests pass, but
  autogenerate drift checking is unavailable.
- Impact: a future schema-model change can omit a migration without an
  automated warning.
- Remediation: define/import authoritative metadata into `alembic/env.py`, add
  naming conventions if needed, and gate `alembic check` in CI.

#### QA-GIT-001 — The public repository's main branch is unprotected

- Status: resolved and accepted under QA-104
- Confidence: high
- Observed: the GitHub branch API reported `main_protected=false` at the audited
  commit. The latest CI run for the commit succeeded, but direct pushes can
  bypass review and required checks.
- Impact: evidence or governance controls can be replaced without a pull-request
  checkpoint.
- Remediation: protect `main`, require the CI checks, block force pushes and
  deletions, and require conversation resolution where supported.
- Resolution evidence: the GitHub API reports strict required `standard` and
  `transformer-cpu` contexts, pull-request delivery, administrator enforcement,
  linear history, and conversation resolution enabled. Force pushes and branch
  deletion are disabled. The zero-approval single-owner boundary is documented
  without inventing an independent reviewer.

#### QA-SEC-002 — Security checks are manual and not merge gates

- Confidence: high
- Observed: the manual high-confidence current/history scan found zero secrets,
  but there is no dedicated secret scanner, dependency audit, SBOM, container
  scan, or dependency-update configuration in CI. GitHub Action references use
  major tags instead of immutable SHAs.
- Impact: later dependency or credential regressions may merge undetected.
- Remediation: add a sanitized secret scan, `pip-audit`, CycloneDX SBOM,
  container scan, automated dependency updates, and immutable Action pins.
- Resolution evidence: QA-105 adds a redacted full-history Gitleaks gate with
  an ephemeral negative fixture, strict target-platform PyPI audits,
  privacy-checked CycloneDX SBOMs, an explicit hash-locked non-PyPI Torch SBOM
  boundary, Trivy enforcement on the upgraded digest-pinned PostgreSQL image,
  weekly Dependabot updates, and immutable Action commits. GitHub Actions run
  30162536790 passes `standard`, `transformer-cpu`, and `security`; the branch
  API reports all three as strict required `main` contexts.

#### QA-TYPE-001 — No static type-checking gate exists

- Confidence: high
- Observed: the source uses extensive annotations and protocols, but no mypy or
  Pyright configuration or CI job exists.
- Impact: interface drift and nullable/dynamic errors remain dependent on
  runtime path coverage.
- Remediation: adopt one checker incrementally, establish a clean scoped
  baseline, and ratchet it across production modules.

#### QA-MAINT-001 — Critical orchestration is concentrated in large functions

- Confidence: medium
- Observed: `cli.py` is 598 lines and its `main` function is approximately 375
  lines. `transformer_fit.py` and `transformer_calibration.py` exceed 1,000
  lines; several orchestration functions are about 180–209 lines.
- Impact: review, isolated testing, error-path reasoning, and future feature
  changes are harder than necessary.
- Remediation: extract command handlers and pure validation/report builders in
  small behavior-preserving changes after higher-priority controls.

#### QA-DATA-001 — Retention deletion is governed but operationally manual

- Confidence: high
- Observed: raw data is correctly ignored and the cleanup command is tested,
  but cleanup remains a maintainer responsibility due by 2026-11-19 with no
  scheduled reminder or automated deadline check.
- Impact: human omission could retain sensitive source narratives beyond the
  approved local period.
- Remediation: add a local preflight/deadline check and calendar/runbook
  checkpoint without uploading or backing up the data; preserve deletion
  evidence after cleanup.

### Low

#### QA-SERIAL-001 — Trusted-local artifacts use executable serialization

- Confidence: medium
- Observed: the baseline uses `joblib.load`; transformer resume state uses
  `torch.load(..., weights_only=False)`. Paths, byte counts, and hashes are
  checked before governed loads, and artifacts are ignored/local-only, which
  materially narrows exposure. Hashes provide integrity, not authenticity, if
  an attacker can replace both artifact and manifest.
- Remediation: document the trusted-local-only boundary, never accept uploaded
  artifacts, prefer non-executable formats where practical, and consider
  `weights_only=True`/a split state format for resume data.

#### QA-WARN-001 — Test runs emit dependency deprecation warnings

- Confidence: high
- Observed: each full suite emits five joblib/NumPy deprecation warnings.
- Impact: warning noise can hide future actionable warnings and foreshadows an
  eventual compatibility break.
- Remediation: identify the originating call path, upgrade or patch the bounded
  dependency combination, and add a warning budget after resolution.

#### QA-GOV-001 — Standard public-repository security metadata is incomplete

- Confidence: high
- Observed: no `SECURITY.md`, standalone `LICENSE`, `CODEOWNERS`, or
  dependency-update configuration is tracked. `pyproject.toml` intentionally
  states “All rights reserved,” so this is not an accidental open-source grant.
- Impact: vulnerability reporting, paper artifact reuse, ownership, and reuse
  permissions are less clear to outside reviewers.
- Remediation: add a security policy and ownership metadata; decide whether the
  code and eventual paper artifacts remain all-rights-reserved or receive
  explicit licenses.
- Resolution evidence: QA-105 tracks SECURITY.md, repository-wide CODEOWNERS,
  an explicit all-rights-reserved inspection-only LICENSE, and weekly pip,
  Actions, and Docker Dependabot configuration. Contract tests and run
  30162536790 verify the tracked controls.

## Evidence readiness matrix

Readiness labels distinguish improvable engineering gaps from deliberately
closed evidence boundaries. `Bounded` is not a weaker version of `Strong`; it
means the project correctly refuses to make a claim its protocol cannot support.

| Evidence area | Current readiness | Evidence now available | Remaining upgrade or paper treatment |
|---|---|---|---|
| Data lineage and privacy | Strong | aggregate reconciliation, ignored raw data, manifest/hash checks, zero high-confidence Git secret hits | describe local-retention limitation and complete deletion by 2026-11-19 |
| Validation metrics | Strong | independent 119/119 aggregate replay; class-aware confusion evidence | eligible for an internal draft only after QA-pack acceptance |
| Dependency safety | Strong | accepted patched constraints; strict target-platform audits and privacy-bounded CycloneDX SBOMs run in required CI; hardened PostgreSQL passes actionable HIGH/CRITICAL scanning | review weekly updates, regenerate locks on target platforms, and clear or renew no Trivy exception without fresh evidence |
| Reproducibility | Strong | accepted commit/data/artifact identities plus ten exact-digest locks; clean Windows and Linux standard/transformer replays; isolated hash-enforced CUDA and CPU wheels | dependency changes require target-platform regeneration, audit, and replay |
| Software quality | Improving | Ruff/format/schema/link checks; Windows suites; separate hash-locked Linux jobs; remote run 30161131645; protected PR delivery requiring both checks | QA-106 coverage ratchet, QA-107 schema drift, and QA-108 typing remain open |
| Frozen-test performance | Bounded—not evaluated | split identity and aggregate test count only; no predictions or metrics | do not report or imply performance; new policy approval is required before access |
| Operational automation | Bounded—manual only | no validation threshold passed every class-aware gate | present the negative selective-classification result; do not imply routing authorization |
| Fairness | Bounded—not assessed | fairness limitation and prohibited claim are documented | do not claim demographic fairness; any future study needs approved attributes and governance |
| Production impact | Bounded—not applicable | no active API, frontend, monitoring, or deployment | do not claim productivity, service reliability, or production impact |

## Recommended disposition

QA-SEC-001 and QA-REPRO-001 are accepted and resolved by QA-101 and QA-102.
QA-103 through QA-105 now protect the selected-model path, evidence branch, and
software supply chain. Add the QA-106 coverage/warning ratchet next, then restore
Alembic drift detection under QA-107. Lower-priority refactoring should wait
until those behaviors are protected.

The audit report should be marked accepted only after the owner confirms the
finding inventory and remediation order. Paper literature research and drafting
then proceed against that accepted snapshot; they do not change the model,
threshold policy, test boundary, or release decision.

## Limitations of this audit

- The high-confidence secret scan is pattern-based, not a proof that no
  arbitrary secret exists; a dedicated entropy/provider-aware scanner is a
  recommended control.
- GitHub vulnerability-alert configuration returned HTTP 401 without repository
  administration credentials, so its enabled state was not asserted.
- The CUDA torch wheel is outside PyPI and was skipped by `pip-audit`.
- Dynamic GPU training was not rerun; the accepted local artifact was checked by
  hash and covered by existing aggregate reports and tests.
- No service penetration or browser accessibility test was applicable because
  the repository has no active API or frontend.
- Aggregate test-partition counts were reconciled from the already-approved
  split state; no test labels, predictions, metrics, threshold search, or
  row-level content were accessed.
