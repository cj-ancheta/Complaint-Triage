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
