# CT-401 abstention threshold analysis

## Purpose

CT-401 turns the accepted ADR 0016 policy into a reproducible, aggregate-only
validation analysis. It does not approve a threshold, access the frozen test
partition, authorize deployment, or promote portfolio metrics.

The command evaluates calibrated MiniLM confidence on the already-used October
2024 validation partition. It proposes a threshold only when every global and
class-aware gate passes. Otherwise, it records the accepted
`manual_review_only` fallback.

## Workflow

1. Start from the accepted CT-306 operational model-selection report.
2. Resolve the linked calibration, transformer, and split evidence by the same
   run ID.
3. Validate every source against its JSON Schema and reconcile all source and
   artifact hashes.
4. Verify the model and calibrator artifacts before loading either artifact.
5. Require a clean, 40-character Git implementation commit before inference.
6. Query only included October validation rows:
   `2024-10-01 <= date_received < 2024-11-01`.
7. Reproduce the accepted calibrated October record count, accuracy, negative
   log-likelihood, and multiclass Brier loss within an absolute `1e-5`
   tolerance.
8. Evaluate the no-abstention reference (`0.0`) and the fixed candidate grid
   (`0.50` through `0.95` in `0.05` increments), using
   `confidence >= threshold`.
9. Apply all accepted global and class-aware gates and the deterministic
   tie-break order.
10. Write one aggregate-only, schema-validated report atomically under
    `data/evaluations/cfpb/abstention/`.

The implementation refuses to run inference from a dirty worktree. This makes
the report's `analysis_implementation_commit_sha` replayable and means the
implementation must be reviewed and committed before the real October run.

## Command

From the repository root, after the implementation commit is clean:

```powershell
.\.venv-transformer\Scripts\complaint-triage.exe analyze-abstention `
  --model-selection-report data/evaluations/cfpb/model-selection/cfpb-run-20260722T130728Z-2b7815d4c850-operational-model-selection-1.0.0.json
```

Do not run this command before the implementation review checkpoint is
approved. The command needs the governed local model and calibrator artifacts,
the local PostgreSQL analytical data, and the pinned CUDA environment.

## Report evidence

For each threshold the report records:

- suggestion and review counts;
- coverage, review rate, selective accuracy, selective risk, and false and
  correct suggestion rates;
- a Wilson 95% interval for selective accuracy;
- actual-class support, coverage, and conditional accuracy;
- predicted-class suggestion count, precision, and Wilson 95% interval;
- an aggregate suggested-only confusion matrix;
- every gate result and final eligibility.

No narrative, complaint ID, token ID, row-level logit, probability, prediction,
or threshold outcome is written to the report or controlled error output.

## Selection and review boundary

Eligible candidates are ordered by highest coverage, then highest selective
accuracy, lowest false-suggestion rate, and lower threshold. The resulting
value is only a proposal. `selected_threshold_owner_approved` remains `false`,
and the frozen test boundary stays closed until a separate explicit approval.

If no candidate passes, the output status is `manual_review_only`. Changing the
grid, gates, fallback, or selection order requires a new reviewed policy rather
than an ad hoc rerun.

## Synthetic validation

The test suite covers a fully eligible population, the no-eligible-candidate
fallback, inclusive threshold equality, fixed-grid rejection, Wilson intervals,
schema validation, deterministic report replay, clean-commit enforcement, CLI
safe errors, and source-level confirmation that the query contains October
validation boundaries but no test or September boundary.

Synthetic tests inject inference arrays and never connect to PostgreSQL, load
the model artifact, or touch real row values. The real October analysis remains
a separate post-commit execution step.

## Accepted CT-401 evidence

Charles accepted the CT-401 report and its `manual_review_only` conclusion on
2026-07-25. The command ran from clean implementation commit
`6866ee17242534d23a7dd1350092a420662b6c78` and evaluated all 41,831 expected
October validation records. It reproduced the accepted accuracy exactly; the
observed NLL and multiclass Brier loss were within the fixed `1e-5` absolute
tolerance.

No candidate passed every ADR 0016 gate. Threshold `0.75` reached 85.6279%
coverage and 93.6402% selective accuracy but exceeded the false-suggestion
ceiling at 5.4457% and produced only four suggestions for the least-suggested
class. Threshold `0.80` passed the global accuracy, coverage, and
false-suggestion gates but made zero suggestions for one predicted class, so it
failed the class-aware count and precision protections. Higher thresholds did
not repair that class exclusion; `0.95` also fell below the global coverage and
actual-class coverage floors.

The accepted report is
`data/evaluations/cfpb/abstention/cfpb-run-20260722T130728Z-2b7815d4c850-abstention-threshold-analysis-1.0.0.json`
with SHA-256
`73092c7fba0c069ba0d1a8b419e5203db3ffc8ed6f245000685b87e20e526716`.
It contains no row values, and both September and the frozen test partition
remain untouched by CT-401. No threshold, deployment, or portfolio promotion
is authorized.
