# Research paper workspace

Status: full internal validation-only manuscript drafted; publication review
pending

Working title: **When Aggregate Accuracy Is Not Enough: A Governance-Aware
Validation Study of Financial Complaint Triage**

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

## Drafting workflow

1. Freeze the evidence map against accepted snapshot `2d886756...`.
2. Collect primary literature and record claim-level support, not just a list of
   related papers.
3. Generate tables and figures only from committed aggregate JSON.
4. Draft methods before results so selection and eligibility rules cannot be
   rewritten after seeing outcomes. **Complete.**
5. Draft results as validation/tuning evidence, including the unsuccessful
   abstention outcome. **Complete.**
6. Run citation, schema, link, privacy, and prohibited-claim checks.
7. Require a separate owner review before calling the document publication-ready.

No step in this workflow authorizes frozen-test access, model retraining, a new
threshold search, deployment, or public promotion of the validation metrics as
final performance.
