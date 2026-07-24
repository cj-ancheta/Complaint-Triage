# Validation model comparison

CT-304 compares the accepted TF-IDF logistic-regression candidate and the
accepted MiniLM epoch using only their existing aggregate validation reports.
It does not query PostgreSQL, load either fitted artifact, or access the frozen
test partition.

## Fixed comparison boundary

The command first validates both source reports against their closed schemas.
It then requires matching run IDs, split-manifest hashes, training and
validation counts, ordered labels, narrative-only feature inputs, and untouched
test declarations. The selected TF-IDF candidate must exist and have converged;
the selected transformer epoch must also exist.

The directly comparable validation dimensions are accuracy, macro F1, weighted
F1, worst-class recall, and per-class precision, recall, and F1. Every reported
delta is `transformer - baseline`, so a positive quality delta favors MiniLM.
Artifact byte counts are compared directly.

Training time is retained only as scoped evidence. The TF-IDF value measures
the selected candidate's fit, while the transformer value sums all completed
training and validation epochs. The report deliberately does not calculate a
runtime ratio from those unlike measurements. Likewise, top-2 accuracy is not
compared because the accepted baseline selection report does not contain it.

## Utility boundary

CT-304 may propose which candidate advances to validation-only calibration in
CT-305. It cannot select or promote the final operational model. Calibration,
abstention behavior, CPU inference latency, comparable runtime memory,
explainability, operational complexity, and deployment cost remain inputs to
the written CT-306 utility ADR.

This means a MiniLM quality lead is evidence for calibrating MiniLM next, not a
claim that it is already the best deployment choice. The frozen test set remains
untouched and `portfolio_promotion_approved` remains false.

## Accepted validation evidence

The comparison was generated from clean implementation commit
`f577da97873b08284e5274fc78c8e2ed4fa4fb7b`. Both source reports identify split
manifest SHA-256
`8685eefd10d764d813dee2891e930323c22592850d537b0571956f390afe554b`,
394,564 training rows, 80,992 validation rows, the same eleven labels, and no
test access.

| Validation metric | TF-IDF logistic regression | MiniLM epoch 3 | MiniLM minus TF-IDF |
|---|---:|---:|---:|
| Accuracy | 0.883692 | 0.8858529237 | +0.0021609237 |
| Macro F1 | 0.699661 | 0.7357461057 | +0.0360851057 |
| Weighted F1 | 0.879291 | 0.8866921404 | +0.0074011404 |
| Worst-class recall | 0.057269 | 0.2070484581 | +0.1497794581 |

MiniLM has higher F1 for ten of eleven classes. TF-IDF retains a small F1 lead
for Mortgage. The shared weakest-recall class is Debt or credit management;
MiniLM raises its recall from 0.057269 to 0.2070484581 and its F1 from 0.106996
to 0.2772861357.

The retained TF-IDF pipeline is 19,625,755 bytes and the retained MiniLM weights
are 133,480,388 bytes, making MiniLM 6.801287 times larger. The report records
75.573 seconds for the selected TF-IDF candidate fit and 5,292.732 seconds for
all three MiniLM training-and-validation epochs, but does not treat these
different scopes as a benchmark.

The proposed next action is
`advance_transformer_to_ct305_calibration`. The final operational model remains
null and deferred to CT-306. The generated report SHA-256 is
`9623346c2feb6489b7a8637157142692e6b847bbcc11ea3809ea4b4c5aca04a3`.
Charles accepted this CT-304 evidence and its bounded proposal on 2026-07-24.

## Reproducible command

After the implementation is committed and the worktree is clean:

```powershell
complaint-triage compare-validation-models `
  --baseline-report data/evaluations/cfpb/tfidf-logreg/cfpb-run-20260722T130728Z-2b7815d4c850-tfidf-logreg-selection-1.0.0.json `
  --transformer-report data/evaluations/cfpb/transformer/cfpb-run-20260722T130728Z-2b7815d4c850-transformer-minilm-selection-1.0.0.json
```

The versioned report is written below
`data/evaluations/cfpb/model-comparison/`. Repeating the command with unchanged
source reports returns the existing validated report. Changed source-report
bytes at the same report identity fail closed.
