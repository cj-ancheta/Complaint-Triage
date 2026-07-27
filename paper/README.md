# Research paper workspace

Status: publication-ready public preprint authorized; empirical results remain
validation-only

Title: **When Aggregate Accuracy Is Not Enough: Decision Impact, Validation
Governance, and a Causal Evaluation Blueprint for Financial Complaint Triage**

This workspace turns the accepted repository evidence into a research-style
case study. The intended contribution is not a state-of-the-art performance
claim. It is a reproducible account of what changes when an imbalanced text
classification project treats temporal separation, duplicate isolation,
calibration, class-aware abstention gates, privacy, and software assurance as
part of the empirical method.

## Research questions

1. How do a TF-IDF logistic-regression baseline and a compact MiniLM classifier
   compare on a duplicate-isolated temporal validation partition?
2. What changes when the selected transformer's probabilities are temperature
   scaled and assessed on the later month of the validation period?
3. Can a fixed confidence-abstention policy satisfy both global utility and
   minimum per-class safeguards?
4. Which repository controls are necessary before the resulting evidence is
   credible enough for a portfolio research case study?
5. What prospective design and causal estimands would be required to determine
   whether governed model suggestions improve reviewer decisions without
   worsening any required route?

## Files

- [`manuscript.md`](manuscript.md) is the full research-style draft.
- [`evidence_inventory.md`](evidence_inventory.md) maps each planned claim to
  accepted aggregate evidence and its limitations.
- [`outline.md`](outline.md) defines every paper section, paragraph purpose,
  evidence input, and literature need.
- [`claim_rules.md`](claim_rules.md) controls wording, metrics, privacy, and
  prohibited inferences.
- [`table_figure_plan.md`](table_figure_plan.md) specifies reproducible tables
  and figures without row-level data.
- [`literature_questions.md`](literature_questions.md) is the search protocol
  for the primary-source claim matrix.
- [`references.md`](references.md) contains the verified bibliography and a
  scope note for every source.
- [`claim_source_matrix.md`](claim_source_matrix.md) maps manuscript claims to
  those sources and records the limits of each citation.
- [`generated/result_tables.md`](generated/result_tables.md) and its source
  manifest are deterministic aggregate-only outputs. Regenerate them with
  `python paper/scripts/generate.py`.
- [`publication_readiness.md`](publication_readiness.md) records completed
  checks and the bounded public-release authorization.
- [`prospective_causal_protocol.md`](prospective_causal_protocol.md) specifies
  the target trial, estimands, DAG interpretation, outcomes, analysis, and
  stopping rules; it is a design blueprint, not a conducted experiment.
- [`publication_checklist.md`](publication_checklist.md) records the final
  evidence, causal, privacy, metadata, and release gates.
- [`impact_statement.md`](impact_statement.md) gives the decision and causal
  relevance in publication-ready plain language.
- [`submission/README.md`](submission/README.md) is the DOI-deposit and
  external-submission handoff, including immutable-file and rights checks.
- [`submission/finalization_status.md`](submission/finalization_status.md)
  records the one remaining account-bound input and the enforced final gate.

## Drafting workflow

1. Freeze the evidence map against accepted snapshot `2d886756...`.
2. Collect primary literature and record claim-level support, not just a list of
   related papers.
3. Generate tables and figures only from committed aggregate JSON.
4. Draft methods before results so selection and eligibility rules cannot be
   rewritten after seeing outcomes. **Complete.**
5. Draft results as validation/tuning evidence, including the unsuccessful
   abstention outcome. **Complete.**
6. Run citation, schema, link, privacy, causal-boundary, and prohibited-claim
   checks. **Complete.**
7. Require a separate owner review before calling the document
   publication-ready. **Authorized 2026-07-26.**
8. Publish the protected, tagged preprint release with the validation-only and
   not-conducted causal-study boundaries intact.
9. Reserve the Zenodo DOI before final publication and place it in the reviewed
   manuscript, citation, and deposit metadata.
10. Build the DOI-bearing `paper-v1.0.2` tag with
    `paper/scripts/build_submission.ps1`; deposit only the exact allowlisted
    directory after both automated verification passes.

Publication authorizes the paper and its explicitly labelled validation
evidence. It does not authorize frozen-test access, model retraining, a new
threshold search, deployment, or promotion of the validation metrics as final
performance.
