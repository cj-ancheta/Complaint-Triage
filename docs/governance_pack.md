# Complaint Triage Governance Pack

- Pack version: `governance-evidence-pack-1.0.0`
- Research run: `cfpb-run-20260722T130728Z-2b7815d4c850`
- Review date: 2026-07-25
- Review status: accepted by Charles Jr Ancheta on 2026-07-25
- Decision: `manual_review_only_research_evidence`

## Executive summary

This repository demonstrates a governed data-science workflow for financial
complaint product classification. It reconciles a bounded public CFPB dataset,
prevents exact duplicate leakage across temporal partitions, compares classical
and compact transformer candidates, calibrates confidence, benchmarks CPU use,
and applies a predeclared abstention policy.

The governance result matters more than the headline metric: no confidence
threshold passed every global and class-aware gate. At threshold `0.80`, global
coverage, selective accuracy, false-suggestion rate, and every actual-class
coverage gate passed, but one valid predicted class received zero suggestions.
The policy therefore rejected automation rather than concealing class exclusion.

## Release decision

| Decision | Status | Reason |
|---|---|---|
| Research model candidate | Selected: calibrated MiniLM | Passed predeclared validation quality, calibration, CPU, evidence, explainability-boundary, and complexity gates |
| Operational threshold | None | No threshold passed every ADR 0016 gate |
| Automated routing | Not authorized | Accepted fallback is `manual_review_only` |
| Frozen test access | Not authorized | No eligible threshold exists to approve |
| API or web deployment | Not authorized | Service, security, monitoring, and provider gates are incomplete |
| Public metric promotion | Not authorized | Evidence is validation-only and claims flags remain false |
| Reviewer productivity/impact claim | Not authorized | Neither was measured with real stakeholders |

The safe state is manual review of every complaint. A future class-specific
threshold or relaxed gate would be a new policy, not an interpretation of the
current results, and must be approved before implementation or data access.

## Required governance documents

- [Problem statement](problem_statement.md): supported decision, users, harms,
  non-goals, and current evidence boundary.
- [Data sheet](data_sheet.md): source context, transformations, distribution,
  privacy, retention, and lineage.
- [Model card](model_card.md): model identity, intended/prohibited uses,
  validation evidence, threshold outcome, limitations, and maintenance.
- [Risk register](risk_register.md): modelling, operational, security, privacy,
  monitoring, and claims risks.
- [Human oversight](human_oversight.md): triggers, reviewer controls,
  escalation, audit records, and responsibility boundaries.
- [Change management](change_management.md): versioning, promotion tests,
  approvals, rollback, and emergency changes.
- [Security assessment](security.md): trust boundaries, threat model, current
  controls, gaps, and incident response.
- [Machine-readable evidence index](governance_evidence.json): closed decision,
  document list, evidence paths, and verified SHA-256 values.

## Evidence lineage

All items below are aggregate and Git-safe. The governance test re-hashes each
file against [`governance_evidence.json`](governance_evidence.json).

| Evidence | SHA-256 | Decision supported |
|---|---|---|
| Population report | `36bae4066aae0cba826b46f24ae2158c9432da231e95bf7eb0a2a70ca25c3b88` | 979,995 staged; 979,194 English eligible; retention and privacy |
| Split manifest | `8685eefd10d764d813dee2891e930323c22592850d537b0571956f390afe554b` | 561,342 canonical rows; temporal boundaries; zero exact fingerprint overlap |
| TF-IDF selection | `c2bc40bda7c17168de6a01157fe4a4cdcd555afe5de200d47df50be936c1ae6e` | Converged classical reference and validation metrics |
| Baseline error analysis | `4f6718ff9d8f1556c40dfc89f7b2b74e4c4cf5eefaa76a8f0c07cee340827c07` | Class, confusion, month, length, and rarity limitations |
| MiniLM selection | `b55188c31a9d28d0eaa424a1208578a9454368098cc803d3aebb87f8a2bd8cef` | Epoch 3 training/validation evidence and artifact identity |
| Model comparison | `9623346c2feb6489b7a8637157142692e6b847bbcc11ea3809ea4b4c5aca04a3` | Shared quality comparison and per-class trade-offs |
| Calibration | `faa1125b99e5dbc9421628102b21e330940700952bbc501bee2cd2bdc46e655e` | Temperature and October calibration evidence |
| Operational model selection | `e4ca24d08a327f2336c006777774142d3b32d120170c50d81ab01dbde54748a7` | Candidate utility gates and CPU benchmark |
| Abstention analysis | `73092c7fba0c069ba0d1a8b419e5203db3ffc8ed6f245000685b87e20e526716` | No eligible threshold and accepted manual-only fallback |

Model and calibrator binaries remain ignored local artifacts. Their hashes and
byte counts are carried inside the accepted reports; the binaries are not part
of this Git-safe pack.

## AI Verify theme mapping

| Governance theme | Evidence in this pack | Open boundary |
|---|---|---|
| Transparency | Problem statement, data sheet, model card, evidence index | No public UI disclosure has been tested |
| Explainability | Global/per-class errors and explicit ban on causal transformer explanations | No local explanation is authorized |
| Reproducibility | Versioned reports, source/artifact hashes, clean commits, replay tests | Row-level reproduction ends after deletion |
| Safety and robustness | Fail-closed commands, abstention gates, risk register, rollback | Adversarial/service testing not implemented |
| Security | Threat model and current control inventory | API/auth/rate-limit/HTTPS controls not implemented |
| Fairness | Class-aware gates and explicit demographic limitation | Demographic fairness not assessed |
| Data governance | Data sheet, append-only lineage, retention/deletion policy | Cleanup evidence is due by 2026-11-19 |
| Accountability | Approval gates, roles, change and oversight policies | Real organizational roles are not appointed |
| Human agency | Manual-only outcome, override/escalation design | No reviewer workflow has been operationally tested |
| Societal/environmental | Source/impact limitations and training runtime disclosure | Energy, carbon, productivity, and downstream harm unmeasured |

## Privacy and data boundary

The pack contains no complaint narratives, complaint IDs, row predictions,
tokens, logits, or row-level threshold decisions. Raw/intermediate text, local
PostgreSQL data, model artifacts, and tokenizer caches remain outside Git under
ADR 0009. The data deletion deadline is 2026-11-19 end of day in Singapore.

A future public demo must not retain arbitrary text without a separate approved
policy. Browser code must never receive server secrets, local artifact paths, or
privileged database/API credentials.

## Reviewer path

A governance or recruiting reviewer can assess the project in this order:

1. Read the release decision above.
2. Read the model card's evaluation and abstention sections.
3. Inspect the threshold evidence report and its failed gates.
4. Review the rare-class and automation-bias risks.
5. Confirm that oversight falls back to manual review.
6. Run `pytest tests/test_governance_pack.py -q` to verify documents, release
   constants, evidence paths, and hashes.

## Closed evaluation boundary and unresolved gates

- CT-402 is closed as `not applicable` under the accepted `manual_review_only`
  fallback; the frozen test remains sealed because no eligible threshold exists.
- No final generalization result exists.
- API authentication, input limits, rate limiting, logging, CORS, HTTPS,
  deployment provider, and cost are unapproved or unimplemented.
- No reviewer usability, override, productivity, downstream harm, drift, or
  monitoring effectiveness evidence exists.
- No metric is approved for README, portfolio, resume, or UI promotion.

The remaining gaps are release blockers, not backlog details to hide. Closing
CT-402 removes a stale workflow status; it does not convert research into a
production claim or imply that final evaluation occurred.
