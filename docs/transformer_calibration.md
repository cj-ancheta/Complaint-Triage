# Transformer probability calibration

CT-305 applies the accepted ADR 0014 boundary to the retained epoch-3 MiniLM.
It fits one positive scalar temperature on September 2024 validation logits and
assesses the result once on October 2024 validation logits. It does not access
test, select an abstention threshold, or choose the final operational model.

## Why this is a separate step

Classification quality asks whether the highest-scoring route is correct.
Calibration asks whether a confidence such as 0.80 behaves like an 80% success
rate over comparable cases. A positive scalar temperature changes the softness
of the probability distribution without changing logit order, so CT-305 can
improve confidence interpretation without silently changing the accepted class
predictions.

The command uses the exact CT-303 validation ordering and FP16 inference path.
It verifies the accepted transformer report, comparison report, split manifest,
and model artifact before inference. The complete recomputed confusion matrix
and top-2 result must reproduce epoch 3 before calibration is allowed.

## Evidence boundary

- Calibration fit: `2024-09-01 <= date_received < 2024-10-01`, 39,161 rows.
- Calibration assessment: `2024-10-01 <= date_received < 2024-11-01`, 41,831 rows.
- Test: inaccessible.
- Logits, probabilities, narratives, tokens, dates, and row identities: memory
  only and never written.
- Scalar calibrator: ignored local artifact governed through 2026-11-19.
- Aggregate report: commit-safe under `data/evaluations/cfpb/calibration/`.

Negative log-likelihood is the fitting objective and primary assessment metric.
The report also includes multiclass Brier loss, confidence gap, fixed-width and
equal-mass top-label ECE, fixed-width reliability bins, and per-class October
probability diagnostics. ECE is diagnostic because its estimate depends on the
binning method.

## Reproducible command

Run only from the isolated transformer environment after the implementation is
committed and the worktree is clean:

```powershell
.\.venv-transformer\Scripts\python.exe -m complaint_triage calibrate-transformer `
  --transformer-report data/evaluations/cfpb/transformer/cfpb-run-20260722T130728Z-2b7815d4c850-transformer-minilm-selection-1.0.0.json
```

The report proposes calibrated probabilities for CT-306 only if October NLL
improves, October Brier stays within the accepted guard, probabilities remain
valid, predictions and top-2 membership remain unchanged, and all lineage and
population checks pass. CT-306 still owns the final utility decision.

## Accepted calibration evidence

The governed run completed on 2026-07-25 from clean implementation commit
`753b61a9a81b9c1b403af27e75588507a52582b3`. It reproduced the accepted epoch-3
confusion matrix and original PyTorch FP16 top-2 result across all 80,992
validation rows before fitting a temperature of `1.041049944456901`.

| October validation metric | Before | After | Change |
|---|---:|---:|---:|
| Negative log-likelihood | 0.3714538016 | 0.3698036697 | -0.0016501319 |
| Multiclass Brier loss | 0.1777332810 | 0.1770533041 | -0.0006799768 |
| Equal-width top-label ECE, 15 bins | 0.0238944672 | 0.0173362285 | -0.0065582386 |
| Equal-mass top-label ECE, 15 bins | 0.0235984646 | 0.0179463118 | -0.0056521529 |
| Signed confidence minus accuracy | 0.0234235903 | 0.0166845511 | -0.0067390391 |

October NLL improved by 0.4442% and multiclass Brier by 0.3826%. Equal-width
and equal-mass ECE improved by 27.45% and 23.95% respectively. Accuracy and
top-k rankings remained unchanged, as required.

The class diagnostics are more mixed. One-versus-rest Brier improved for nine
of eleven labels, while it worsened slightly for Credit reporting or other
personal consumer reports and Debt or credit management. The absolute gap
between each class's mean predicted probability and prevalence also worsened
slightly for every label. This does not violate the approved global eligibility
rule, but it demonstrates that one scalar temperature does not solve
class-specific calibration and must remain visible in CT-306.

All fixed eligibility checks passed. The report therefore proposes
`calibrated_transformer_probabilities` for CT-306 while leaving the final model
and abstention threshold unselected and test untouched. GPU inference took
102.825 seconds.

The generated report SHA-256 is
`faa1125b99e5dbc9421628102b21e330940700952bbc501bee2cd2bdc46e655e`.
The ignored scalar artifact SHA-256 is
`3fc439322d7bc32d7f0bfbdef6f5383bfc0867e595bad340340aba9909a66800`.
Charles accepted the CT-305 evidence, eligibility outcome, and documented
class-specific limitation on 2026-07-25.
