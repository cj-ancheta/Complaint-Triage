# Majority reference baseline

CT-204 implements report version `majority-baseline-1.0.0`. It is the simplest
honest benchmark for the complaint-routing task: learn the single most common
label from training counts and predict that label for every row.

This baseline is intentionally weak. Its purpose is to expose how misleading
accuracy can be under severe class imbalance and to establish a floor that later
models must beat on balanced metrics.

## Leakage boundary

The predicted label is selected from `train` counts only. Validation and test
counts never influence the label, a parameter, a threshold, or a tie-break. A
tie for the largest training class fails closed instead of making an arbitrary
selection.

The frozen predictor is evaluated unchanged on train, validation, and test. ADR
0010 permits the test evaluation because this reference has no tunable
parameter. CT-205 and later tuning must continue to leave test outcomes
untouched until the final evaluation gate.

## Input and privacy

The command reads only the accepted metadata-only CT-203 split manifest. It does
not require PostgreSQL and never reads narratives, complaint IDs, row lineage,
or individual fingerprints.

The generated report includes:

- the training-selected label;
- class distributions for traceability;
- accuracy, macro precision, macro recall, macro F1, and weighted F1;
- precision, recall, F1, support, and confusion counts for every one of the
  eleven labels; and
- an 11-by-11 confusion matrix for each split.

All metrics are rounded to six decimal places only after calculation. Classes
with no correct prediction remain explicit zeroes and are included in macro
averages.

## Run

From a clean implementation commit:

```powershell
.\.venv\Scripts\complaint-triage.exe evaluate-majority-baseline `
  --split-manifest data/manifests/cfpb/splits/<run-id>-split-1.0.0.json
```

The output is written under `data/evaluations/cfpb/majority/`. Rerunning against
the same split verifies the stored source hash and calculated metrics and returns
the identical report.

## Interpretation

Accuracy equals the prevalence of the selected majority label. It does not mean
the classifier routes all products well. Macro F1 gives every accepted product
equal weight, so ten zero-performing classes remain visible. Weighted F1 adds
operational context but is still dominated by high-volume labels.

The test result is issue evidence only until Charles explicitly approves any
metric for README, portfolio, or resume use.

## Verify

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
.\.venv\Scripts\pytest.exe -q
```

The focused tests prove training-only selection even when later splits have a
different majority, fail-closed ties, exact metric arithmetic, zero-score class
retention, confusion-matrix orientation, idempotent output, schema validation,
and privacy flags.

## First retained-run evaluation

The first authoritative evaluation ran on 2026-07-23 from clean implementation
commit `bf60c724f2706f7e6b8700b2d4a3a5a4afc20aeb`. Training selected `Credit
reporting or other personal consumer reports`; the predictor used that same
label unchanged for every row in all three partitions.

| Split | Rows | Accuracy | Macro F1 | Weighted F1 | Macro recall |
|---|---:|---:|---:|---:|---:|
| Train | 394,564 | 0.628699 | 0.070184 | 0.485372 | 0.090909 |
| Validation | 80,992 | 0.666881 | 0.072741 | 0.533607 | 0.090909 |
| Test | 85,786 | 0.667172 | 0.072760 | 0.533980 | 0.090909 |

Accuracy follows majority-label prevalence, while macro recall is exactly one
of eleven classes and ten classes have zero recall. This confirms that the
apparently high accuracy is not useful routing performance; later models must
be judged primarily against balanced and per-class measures.

The canonical report is
`data/evaluations/cfpb/majority/cfpb-run-20260722T130728Z-2b7815d4c850-majority-baseline-1.0.0.json`.
Its source hash, metric tables, three confusion matrices, schema, and privacy
flags reconcile, and replay is byte-identical. These scores remain CT-204 review
evidence and are not approved public portfolio claims.
