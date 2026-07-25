# Bounded orchestration structure

Status: QA-111 accepted; GitHub Actions run 30165661423 passed

QA-111 is a behavior-preserving maintainability change. It does not change the
command names, arguments, report schemas, selection rules, retention policy,
privacy fields, or frozen-test boundary.

## CLI dispatch

The former `cli.main` mixed parser construction and approximately 375 lines of
conditional dispatch. Parser construction now lives in `cli_parser.py`, grouped
into data, baseline, and transformer command families. `cli.main` is two lines;
`dispatch` selects either one declarative ordinary-command adapter or one of
four bounded special handlers for cleanup, acquisition, TF-IDF smoke selection,
and transformer progress streaming.

All 20 parser commands must map to exactly one handler. Existing CLI tests still
characterize success payloads, privacy-safe controlled errors, database-setting
errors, cleanup confirmation, smoke selection, and stderr progress events.

## Transformer phases

`train_transformer` fell from 209 lines to 50. It now coordinates three named
phases:

1. `_prepare_fit` validates lineage/time, loads the pinned runtime, selects the
   batch configuration, and returns immutable preparation state;
2. `_run_training_epochs` owns the CUDA resources, resume state, epoch loop,
   checkpointing, and cleanup; and
3. `_publish_fit` validates and atomically writes the unchanged aggregate
   report.

The calibration orchestrator fell from 205 to 135 lines. Its schema-shaped,
privacy-bounded report construction is isolated in
`_build_calibration_report`, which has no file, environment, or database I/O.
The existing full aggregate calibration/replay test verifies the generated
report and idempotent replay remain unchanged.

## Non-regression ratchets

Repository tests enforce complete one-handler-per-command coverage and upper
bounds on the refactored phase sizes. These are reviewability ratchets, not a
license to satisfy line counts through dense formatting: Ruff formatting and
the behavioral suites remain mandatory. Further decomposition should follow
the same pattern—characterize output first, extract one responsibility, and
keep controlled errors and privacy fields at the public boundary.

GitHub Actions run
[`30165661423`](https://github.com/cj-ancheta/Complaint-Triage/actions/runs/30165661423)
passed the standard, CPU-transformer, and security gates with the structural
ratchets and all behavioral characterizations enabled.
