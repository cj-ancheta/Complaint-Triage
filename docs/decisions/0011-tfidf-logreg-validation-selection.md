# ADR 0011: Validation-only TF-IDF logistic-regression selection

- Status: Accepted
- Date: 2026-07-23
- Decision owners: Charles Jr Ancheta and project maintainer
- Scope: CT-205 report `tfidf-logreg-selection-1.0.0`

## Context

CT-203 provides a deduplicated future-facing split with 394,564 training rows,
80,992 validation rows, and 85,786 frozen test rows. CT-204 establishes a
constant majority reference, but it has no text features and cannot route ten
of the eleven classes. CT-205 needs a credible sparse-text baseline with a
small, auditable search space. The search must not inspect the test partition.

The retained complaint narratives and any vocabulary derived from them remain
governed by ADR 0009. A fitted TF-IDF pipeline therefore cannot be committed or
uploaded even when its aggregate evaluation is safe to publish.

## Decision

Use complaint narrative text only. Fit one `TfidfVectorizer` on training rows
with these frozen parameters:

| Parameter | Value |
|---|---|
| n-grams | word unigrams and bigrams `(1, 2)` |
| `min_df` | `5` |
| `max_df` | `0.995` |
| `max_features` | `200000` |
| term frequency | sublinear |
| normalization | L2 |
| matrix dtype | float64 |

Transform validation with that training vocabulary. Never refit or extend the
vocabulary with validation text.

Fit these four multinomial `LogisticRegression` candidates sequentially with
the `saga` solver, L2 penalty, random seed 42, maximum 200 iterations, and
tolerance `0.001`:

| Stable ID | `C` | Class weight |
|---|---:|---|
| `c0p5-unweighted` | 0.5 | none |
| `c1p0-unweighted` | 1.0 | none |
| `c0p5-balanced` | 0.5 | balanced |
| `c1p0-balanced` | 1.0 | balanced |

Select exactly once using validation outcomes and the following ordered rule:

1. exclude candidates that emit a convergence warning;
2. choose the highest macro F1;
3. then the highest worst-class recall;
4. then the highest weighted F1;
5. then the lower `C`; and
6. then the lexicographically lower stable candidate ID.

Comparisons use unrounded scores. Rounding is presentation-only. If no
candidate converges, fail closed. A non-converged candidate can never win even
if its partial-fit metrics are higher.

## Evaluation boundary

CT-205 may read only training and validation rows. It must not query, transform,
score, summarize, or otherwise inspect the test rows. The selected candidate is
not a final portfolio metric until a later, explicitly approved test-evaluation
gate. The aggregate CT-205 report must keep
`portfolio_promotion_approved=false`.

Before the full search, run a small class-stratified smoke fit using training
rows only. The smoke fit writes neither an artifact nor an evidence report and
cannot change the accepted parameters or selection rule.

## Persistence and privacy

Save only the selected fitted pipeline under ignored
`artifacts/cfpb/tfidf-logreg/`. Hash it and record its relative path, byte count,
software versions, and local retention boundary in the report. The artifact
contains a source-derived vocabulary and remains local-only, untracked,
unbacked-up, and governed through 2026-11-19 under ADR 0009.

The commit-safe JSON report may contain configuration, aggregate validation
metrics, per-class aggregate metrics, confusion matrices, convergence status,
timings, matrix dimensions, and artifact metadata. It must not contain tokens,
feature names, coefficients keyed by tokens, narratives, complaint IDs, or row
identities.

## Consequences and limitations

This is an interpretable, reproducible sparse baseline and a useful comparison
point for later models. Class weighting is tested explicitly because the
training distribution is severely imbalanced. Macro F1 leads selection so the
majority class cannot dominate the decision; worst-class recall is the first
tie-break because silent failure on a rare route matters operationally.

The four-candidate grid is deliberately narrow. It does not optimize n-grams,
document-frequency thresholds, regularization beyond two `C` values, or the
vectorizer vocabulary. The reported validation estimate is used for selection
and is therefore not an unbiased final-performance estimate.

## Approval

Charles explicitly approved the fixed vectorizer, four candidates,
convergence gate, ordered validation rule, untouched-test boundary, local-only
artifact, and training-only smoke workflow on 2026-07-23.
