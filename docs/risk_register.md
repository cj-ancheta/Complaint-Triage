# Complaint Triage Risk Register

- Register version: `1.0.0`
- Review date: 2026-07-25
- Current release status: `manual_review_only_research_evidence`
- Risk owner: project/model owner unless a future organization assigns named
  operational owners

## Rating method

Likelihood and impact are qualitative design-review ratings, not measured event
probabilities. Likelihood is `low`, `medium`, or `high` under a hypothetical
deployment. Impact is `low`, `medium`, `high`, or `critical`. A control is
`implemented` only when repository evidence exists; otherwise it is `required`.

The current non-deployment decision is itself a control: it prevents model
outputs from affecting complaint routes. It does not prove that future service
controls would be effective.

## Risk register

| ID | Risk and harm scenario | Likelihood | Impact | Current controls and evidence | Required treatment before deployment | Owner | Status |
|---|---|---|---|---|---|---|---|
| R-01 | Misrouting delays the correct product review or sends a case to the wrong specialist | High | High | Eleven-label contract; temporal evaluation; class metrics; no approved threshold; all cases remain manual | Stakeholder cost matrix, tested reviewer queue, override/escalation, final evaluation, sampled outcome audit | Model owner + operations owner | Blocked by manual-only release |
| R-02 | Overconfident scores cause automation bias even when the predicted route is wrong | High | High | Scalar calibration; reliability evidence; false-suggestion gate; confidence wording rule; threshold grid rejected | UI comprehension testing, confidence training, hidden/secondary score option, override analysis, stop authority | Model owner + UX/operations | Open; no UI authorized |
| R-03 | Product taxonomy, complaint language, or intake mix drifts and invalidates the model | High | High | Versioned 2023 taxonomy/window; temporal split; 2025 shock excluded; change gate | Taxonomy watch, class/input/confidence drift thresholds, delayed-label monitoring, automatic suggestion suspension | Model owner + data steward | Required |
| R-04 | Corrupt, duplicated, poisoned, or mislabeled source records distort training or evaluation | Medium | High | Content hashes; append-only layers; exact schema checks; duplicate-conflict exclusion; source reconciliation | New-run anomaly review, provenance attestations, volume/rate alerts, manual sample audit under privacy controls | Data steward | Partly controlled |
| R-05 | Oversized, empty, binary, malformed, adversarial, or HTML-like input causes failure or unsafe rendering | High | High | Training tokenizer truncates to 384 tokens; safe internal errors; no public endpoint | API body/character bounds, Unicode normalization, content-type validation, HTML escaping, timeouts, adversarial tests | Service owner + security owner | Required |
| R-06 | Repeated queries enable model extraction, membership inference, probing, or abusive use | Medium | High | Artifacts stay local; no API exists; local explanations are not authorized | Authentication decision, rate limits, abuse detection, coarse outputs, query monitoring, incident playbook | Security owner | Required |
| R-07 | Submitted or source narratives containing sensitive circumstances are retained or leaked | High | Critical | Raw data ignored; loopback PostgreSQL; aggregate Git evidence; no raw logging; ADR 0009 deletion deadline | Public-demo no-retention design, privacy notice, log redaction tests, deletion verification, incident response | Data steward + security owner | Partly controlled locally |
| R-08 | Reviewer feedback is manipulated, low quality, or fed back as ground truth and degrades later models | Medium | High | No feedback loop exists; model versions are immutable | Separate suggestion, override, reason, and adjudicated label; access control; audit trail; quality sampling; no automatic retraining | Operations owner + model owner | Required |
| R-09 | Monitoring is absent, delayed, broken, or falsely reassuring while performance deteriorates | High | High | Current non-deployment decision; evidence files are immutable | Monitoring health checks, freshness/completeness alerts, independent stop path, alert ownership and rehearsal | Model owner + service owner | Required |
| R-10 | Vulnerable or drifting Python, model, tokenizer, database, container, or frontend dependency changes behavior or enables compromise | Medium | Critical | Pinned model revision and training environment; artifact hashes; CI lint/tests | Lock production dependencies, SBOM, Dependabot/scanning, image scanning, patch SLA, signed release artifacts | Security owner + maintainer | Required |
| R-11 | Database, model load, service, or provider outage prevents review support or returns inconsistent results | Medium | High | Manual processing is the accepted fallback; commands fail closed | Health/readiness checks, timeout/circuit breaker, queue preservation, rollback image, recovery drill, user-visible unavailable state | Service owner + operations | Required |
| R-12 | Portfolio, UI, resume, or stakeholder language presents validation evidence as final, fair, deployed, or impactful | High | High | Artifact claims flags are false; governance release decision; README metric gate | Claim review checklist, source links, screenshot review, remove unsupported impact verbs, explicit demo labels | Project owner + governance reviewer | Open until every publication is reviewed |
| R-13 | Aggregate performance conceals systematic failure for rare classes or unmeasured demographic groups | High | High | Macro/per-class evidence; actual/predicted class threshold gates; 0.80 rejected for zero rare-class suggestions | Stakeholder harm review, larger rare-class evidence, demographic assessment only with lawful/appropriate data and methods | Governance reviewer + model owner | Material residual risk |
| R-14 | Explanation text exposes sensitive fragments or is mistaken for a causal or legal reason | Medium | High | Transformer local attribution and reason codes are not authorized; global evidence only | Approved explanation vocabulary, privacy review, causal-language ban, reviewer training, redaction tests | Model owner + governance reviewer | Blocked pending design |

## Highest residual risks

The main modelling risk is not hidden: a threshold of `0.80` passed all global
gates but produced zero suggestions for one predicted class. Authorizing that
policy would create route exclusion behind a strong aggregate selective
accuracy. ADR 0016 correctly rejected it.

The main operational risks are unimplemented service controls, automation bias,
privacy of submitted narratives, monitoring failure, and unsupported public
claims. These are not mitigated merely because the offline model and tests work.

## Review and escalation

Review this register before any new data source, taxonomy, model, threshold,
service, frontend, deployment provider, feedback loop, monitoring rule, or public
claim. Any critical incident, unexplained evidence mismatch, retention breach,
taxonomy change, or monitoring outage suspends model suggestions and returns the
system to manual review. See [`change_management.md`](change_management.md) and
[`human_oversight.md`](human_oversight.md).
