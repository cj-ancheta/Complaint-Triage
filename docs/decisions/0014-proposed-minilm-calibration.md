# ADR 0014: Proposed MiniLM probability calibration

- Status: Accepted
- Date: 2026-07-24
- Decision owner: Charles Jr Ancheta
- Scope: CT-305 validation-only calibration of the accepted epoch-3 MiniLM

## Context

CT-304 advances the accepted epoch-3 MiniLM candidate to calibration because it
has higher validation accuracy, macro F1, weighted F1, and worst-class recall
than the selected TF-IDF baseline. That is a quality-only proposal, not a final
operational-model decision. The model's confidence values have not been tested
for calibration and must not yet be interpreted as empirical correctness
probabilities.

The accepted validation period contains 80,992 rows across September and
October 2024. September contains 39,161 rows and October contains 41,831; all
eleven labels occur in both months. The frozen test partition contains 85,786
rows beginning November 2024 and remains inaccessible during CT-305.

Epoch 3 was selected using the complete September-October validation period.
Therefore, even a temporal calibration sub-split is still validation tuning
evidence, not an unbiased final estimate. CT-305 must state this limitation and
keep portfolio promotion disabled.

## Decision proposal

Use one scalar temperature for the accepted MiniLM logits:

```text
calibrated_probability = softmax(logits / temperature)
```

Temperature scaling is preferred to one-versus-rest sigmoid or isotonic
calibration because it naturally produces one normalized multiclass
distribution, introduces only one fitted parameter, and preserves logit order,
argmax predictions, and top-k rankings when the temperature is positive.

Do not compare multiple calibration algorithms or tune this method after
viewing calibration outcomes. Do not change the encoder, classification head,
taxonomy, token boundary, or epoch selection.

## Temporal calibration boundary

Partition the existing validation rows by `date_received`:

| Purpose | Inclusive start | Exclusive end | Expected rows |
|---|---|---|---:|
| calibration fit | 2024-09-01 | 2024-10-01 | 39,161 |
| calibration evaluation | 2024-10-01 | 2024-11-01 | 41,831 |

Fit the temperature only on September logits. Evaluate pre- and
post-calibration probabilities once on October. This later-month evaluation is
the primary calibration evidence. September metrics are reported as fit
diagnostics and cannot be presented as generalization evidence.

Use one canonical validation query that includes `date_received` for the
in-memory partition assignment. It must require `split_assignment =
'validation'`, the accepted run ID, split version, population version, and
included disposition, and retain the CT-302 source ordering. There is no option
to query `test`, choose different dates, or randomize the partition. Reconcile
each month and class count against the already accepted aggregate CT-206
evidence before fitting.

## Model inference and data handling

Verify the accepted transformer report and the SHA-256 and byte count of
`best-model.safetensors` before loading it. Load the immutable MiniLM revision,
apply the retained state dictionary strictly, and reproduce the accepted FP16
validation-inference path on the same CUDA hardware.

Keep logits and integer labels in memory only. Never persist logits,
probabilities, predictions, narratives, complaint IDs, token IDs, dates, or row
identities. The commit-safe report may contain only configuration, aggregate
counts, aggregate metrics, reliability-bin totals, timings, hashes, and safe
claims.

Before calibration, the recomputed combined September-October confusion matrix
and top-2 count must reproduce the accepted epoch-3 report. This proves the
correct weights, label order, preprocessing path, and validation population are
being calibrated. Carry the month partition alongside each in-memory feature
through the existing length-grouping order, but strip it before tokenizer
padding and model inference so the canonical CT-303 batch composition is
unchanged.

## Temperature fitting

Minimize mean categorical negative log-likelihood on September in float64.
Optimize `log(temperature)` with SciPy's bounded scalar minimizer using:

| Parameter | Fixed value |
|---|---:|
| lower temperature | 0.05 |
| upper temperature | 20.0 |
| `xatol` on log-temperature | `1e-8` |
| maximum iterations | 500 |

The logarithmic parameterization guarantees a positive temperature. Fail
closed if optimization does not converge, produces a non-finite value, or
finishes within `1e-6` in log-space of either bound. The unrounded fitted value
is used for every calculation and stored in the artifact.

No new dependency is required: SciPy is already part of the accepted classical
modelling environment and is installed in the isolated transformer environment.

## Calibration metrics

Report these metrics before and after scaling for September and October:

- categorical negative log-likelihood, with lower better;
- unscaled multiclass Brier loss, with range zero to two and lower better;
- accuracy and mean top-label confidence;
- signed mean confidence minus accuracy;
- top-label expected calibration error with 15 equal-width bins; and
- top-label expected calibration error with 15 deterministic equal-mass bins.

The equal-width bins form the commit-safe reliability-diagram data. Each bin
records its fixed interval, row count, correct count, mean confidence,
accuracy, and absolute gap. Empty bins remain present with zero counts and null
summary values. Equal-mass ECE is included because calibration-error estimates
are sensitive to bin construction; neither ECE value is treated as a proper
scoring rule or optimized.

For the October evaluation partition, also report per-class support,
prevalence, mean predicted probability, absolute prevalence gap, and
one-versus-rest Brier loss before and after scaling. These are operational
class diagnostics, not demographic fairness evidence.

Do not select an abstention threshold in CT-305. Confidence-threshold coverage
and selective-accuracy policy require their own declared business trade-off and
remain outside this issue.

## Eligibility proposal for CT-306

The calibrated MiniLM probabilities are eligible for CT-306 only when all of
these fixed checks pass:

1. the September optimizer converges away from its declared bounds;
2. probabilities are finite, lie in `[0, 1]`, and sum to one within `1e-12`;
3. argmax predictions and top-2 membership are unchanged on both months;
4. every partition and class count reconciles;
5. October negative log-likelihood is strictly lower after scaling; and
6. October multiclass Brier loss does not increase by more than `1e-6`.

ECE changes remain diagnostic because binning choices can alter their estimate.
If an eligibility check fails, retain the report and artifact as governed
evidence but propose the uncalibrated MiniLM probabilities for CT-306 instead.
CT-306 still owns the final baseline-versus-transformer utility decision.

## Artifact and report boundary

Write one scalar JSON artifact beneath
`artifacts/cfpb/transformer/<run-id>/calibration/` containing:

- artifact version;
- fitted temperature;
- ordered labels;
- model-artifact SHA-256;
- transformer-report SHA-256;
- split-manifest SHA-256;
- calibration implementation commit SHA; and
- the fixed fit partition and method identifiers.

Hash the artifact and record its relative path and byte count in the report.
Keep it ignored, local-only, unbacked-up, and governed through 2026-11-19 for
consistency with the retained model artifact. Write the closed aggregate report
beneath `data/evaluations/cfpb/calibration/` and permit that report in Git.

Report total GPU inference time and peak CUDA memory, plus CPU optimization
time. These are calibration-run measurements, not serving-latency benchmarks.

## Failure and replay behavior

Require a clean committed implementation before the real run. Use atomic writes
for the calibrator and report. If the report already exists, validate it,
re-verify the source model and calibrator hashes, and return it unchanged. Fail
closed on source-byte changes, unsafe paths, missing artifacts, schema drift,
count mismatch, prediction mismatch, numerical failure, or a partial artifact.

The command must expose controlled aggregate-only errors and keep
`test_accessed=false`, `operational_threshold_selected=false`,
`final_operational_model_selected=false`, and
`portfolio_promotion_approved=false`.

## Consequences and limitations

Temperature scaling can correct global over- or under-confidence but cannot
repair class-specific or input-dependent calibration errors. Because a positive
scalar preserves ranking, it also cannot improve classification accuracy or
rare-class discrimination. The October assessment is temporally later than the
fit month but was previously involved in selecting epoch 3, so it remains
validation evidence. ECE depends on binning, classwise metrics for rare labels
have higher variance, and calibration may drift after deployment.

## Approval

Charles explicitly approved the single-method temperature design, September
fit and October assessment split, optimizer bounds, metric definitions, CT-306
eligibility rule, local artifact boundary, and continued test-set prohibition
on 2026-07-24.

## Primary references

- Guo et al., *On Calibration of Modern Neural Networks*:
  <https://proceedings.mlr.press/v70/guo17a.html>
- Scikit-learn probability-calibration guide, including multiclass temperature
  scaling and independent calibration-data guidance:
  <https://scikit-learn.org/stable/modules/calibration.html>
- Scikit-learn multiclass Brier-loss definition:
  <https://scikit-learn.org/stable/modules/generated/sklearn.metrics.brier_score_loss.html>
- Roelofs et al., *Mitigating Bias in Calibration Error Estimation*:
  <https://proceedings.mlr.press/v151/roelofs22a.html>
- SciPy bounded scalar-minimization API:
  <https://docs.scipy.org/doc/scipy/reference/optimize.minimize_scalar-bounded.html>
