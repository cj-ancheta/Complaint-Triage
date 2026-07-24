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
