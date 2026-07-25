# Repository-wide QA plan

Status: executed; findings awaiting owner review  
Audit date: 2026-07-25  
Audited commit: `1b6130793d7b305605115dea255de15e89d2b94f`

## Purpose

This audit establishes whether the complaint-triage repository is trustworthy
enough to support a research-style case study. It is an engineering and
evidence audit, not an authorization to access the frozen test partition,
deploy a model, automate complaint routing, or promote metrics publicly.

The research-paper boundary begins only after the owner accepts a frozen QA
report and the high-priority remediation decision. Until then, findings are
draft evidence rather than paper claims.

## Questions

1. Does Git contain only safe, reproducible source and aggregate evidence?
2. Do code, tests, schemas, database migrations, reports, and local governed
   artifacts agree with one another?
3. Can the accepted validation metrics be independently reproduced from the
   stored aggregate confusion matrices and threshold counts?
4. Are selected-model, calibration, abstention, privacy, and release claims
   consistent across the specification and governance pack?
5. Which engineering-control gaps must be remediated before the repository is
   used as the evidence base for a paper?

## Scope

The audit covers:

- Git integrity, tracked-file hygiene, ignored-data boundaries, current files,
  and high-confidence secret patterns across current and historical blobs;
- Python syntax, Ruff lint and format checks, package entry points, JSON Schema
  validity, Markdown local-link integrity, maintainability indicators, and
  unsafe-operation patterns;
- the standard and transformer test environments, PostgreSQL integration
  tests, branch coverage, warnings, and CI coverage of supported environments;
- Alembic head/current state, append-only controls, aggregate row
  reconciliation, and duplicate-fingerprint controls;
- raw-shard, model, and calibrator byte/hash reconciliation without reading or
  emitting complaint narratives;
- independent recomputation of validation metrics, comparison deltas,
  calibration lineage, abstention identities, and gate outcomes;
- dependency constraints, installed-environment vulnerability audits,
  reproducibility controls, GitHub branch protection, and repository security
  automation;
- documentation freshness, privacy and retention claims, governance status,
  and paper-readiness limitations.

The audit excludes:

- row-level complaint inspection or qualitative narrative examples;
- any new query against the frozen test partition beyond already-approved
  aggregate split reconciliation;
- retraining, threshold search, policy changes, deployment, or public claims;
- penetration testing of services, because no service is active;
- automatic remediation. Remediation is a separately reviewed workstream.

## Privacy-preserving evidence rules

- Do not print, copy, summarize, or commit complaint narratives or complaint
  identifiers.
- Hash raw and governed local artifacts as byte streams only.
- Query PostgreSQL only for approved aggregate counts, migration state, and
  control metadata.
- Store only Git-safe counts, versions, paths, hashes, statuses, and command
  summaries in QA evidence.
- Preserve the frozen-test boundary and existing manual-review-only release
  decision.

## Workstreams and acceptance criteria

| Workstream | Required checks | Passing condition |
|---|---|---|
| Repository integrity | clean worktree at audit start, `git fsck`, tracked/ignored inventory, large-file check, history secret scan | no corrupt objects, raw data, governed binary artifacts, or high-confidence secrets in Git |
| Static quality | Ruff, formatting, `compileall`, schema checks, local-link checks, complexity survey | all deterministic checks pass; maintainability risks are recorded |
| Tests | standard and transformer suites, PostgreSQL tests, branch coverage, warnings | all applicable tests pass and gaps are quantified |
| Database | sole Alembic head, current revision, integration migrations, aggregate reconciliations, append-only triggers | migration and aggregate identities agree; drift-check limitations are recorded |
| Data/artifacts | raw-shard and governed-artifact byte/hash reconciliation | every referenced local object exists and matches its manifest |
| ML evidence | independent metrics and threshold/gate recomputation | every stored aggregate identity reproduces without production metric helpers |
| Security/supply chain | sanitized secret scan, dependency audit, unsafe loading/process review, CI/security automation inventory | no secret leak; known vulnerabilities and missing controls are triaged |
| Governance/docs | release flags, retention, public-claim boundary, links, stale-claim search | claims are internally consistent and limitations are explicit |

## Severity and confidence

| Severity | Meaning |
|---|---|
| Critical | secret or narrative leak, frozen-test contamination, wrong evaluation, corrupt lineage, or unsafe release decision |
| High | accepted evidence cannot be reliably reproduced, selected-model path is outside CI, or a known exploitable dependency is required |
| Medium | material regression/control gap with an available workaround and no observed evidence corruption |
| Low | defense-in-depth, maintainability, warning, or repository-metadata issue |

Confidence is `high` when directly reproduced by a deterministic command,
`medium` when based on static inspection with clear supporting evidence, and
`low` when environment or access restrictions prevent confirmation.

## Finding lifecycle

Each finding has a stable ID, severity, confidence, workstream, observed and
expected states, evidence, impact, remediation, status, and verification rule.
Allowed states are `open`, `accepted_risk`, `resolved`, and `not_applicable`.
The current report uses `open`; only the owner can accept risk or approve the
remediation sequence.

## Research handoff gate

Paper drafting may start after all of the following are true:

1. the owner reviews the QA report and machine-readable finding inventory;
2. all critical findings are resolved (none were observed in this audit);
3. the owner decides whether each high finding is resolved before drafting or
   carried as an explicit reproducibility limitation;
4. the evidence manifest is marked accepted and its audited commit is frozen;
5. the paper remains validation-only and preserves the manual-review-only,
   no-deployment, no-public-metric-promotion boundary.

## Planned paper structure after QA acceptance

1. Title, abstract, keywords, and contribution statement.
2. Problem context and decision-support boundary.
3. Related work on complaint classification, compact transformers,
   calibration, selective classification, and responsible ML governance.
4. Data source, population, taxonomy, temporal split, duplicate isolation,
   privacy, and retention.
5. Methods: majority reference, TF-IDF logistic regression, compact MiniLM,
   temperature scaling, and threshold gates.
6. Experimental protocol and reproducibility controls.
7. Validation results with uncertainty-aware and per-class interpretation.
8. Selective-classification result and the manual-review-only decision.
9. Repository QA findings and their effect on evidentiary confidence.
10. Threats to validity, limitations, ethics, privacy, and governance.
11. Practical lessons, future work, and conclusion.
12. References, artifact/evidence availability statement, and appendices.

The paper must not contain raw narratives, complaint IDs, unsupported causal
claims, test metrics, production-performance claims, fairness claims, or
productivity claims.
