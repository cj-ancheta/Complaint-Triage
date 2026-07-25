# Operational model selection

CT-306 applies the accepted six-gate utility rule in ADR 0015 to the accepted
TF-IDF logistic-regression pipeline and calibrated MiniLM candidate. It selects
one operational candidate for later abstention, test, API, and governance work.
It does not access test, select an abstention threshold, authorize deployment,
or approve a public metric.

## Why the implementation is committed before timing

The utility thresholds and benchmark procedure are written and approved before
the real CPU measurements. The real command also requires a clean implementation
commit. This prevents the code or thresholds from being quietly changed after
observing which model wins.

## Fixed workload

The benchmark reads only included October 2024 validation narratives from the
accepted run, split, population, and taxonomy. It selects the 512 lowest
normalized-narrative fingerprints, giving a deterministic sample without
choosing rows by label, length, prediction, or timing.

Each candidate runs in a fresh CPU-only subprocess. The first 16 narratives are
an unmeasured warm-up. All 512 narratives are then scored individually for three
passes, producing 1,536 warmed end-to-end measurements per candidate. The
measurement includes vectorization or tokenization, model inference, probability
calculation, and MiniLM temperature scaling. Model load is measured separately.

The subprocess returns aggregate character lengths, latency summaries, peak
process working set, artifact bytes, and environment metadata only. Narratives,
labels, fingerprints, predictions, tokens, sparse vectors, and per-row timings
remain in memory and are not written or printed.

## Decision rule

Calibrated MiniLM is selected only if all six gates pass:

1. evidence and lineage;
2. material validation quality;
3. probability calibration;
4. CPU service usability;
5. explainability boundary; and
6. complexity and cost boundary.

If any gate fails, the accepted TF-IDF pipeline is selected. See
[ADR 0015](decisions/0015-proposed-operational-model-selection.md) for the fixed
thresholds and rationale.

Selective accuracy is explicitly deferred. Both models require an approved
abstention policy, and Phase 4 will select and assess that policy using validation
data before any final test access.

## Reproducible command

After the implementation is committed and the worktree is clean, run from the
isolated transformer environment:

```powershell
.\.venv-transformer\Scripts\python.exe -m complaint_triage select-operational-model `
  --calibration-report data/evaluations/cfpb/calibration/cfpb-run-20260722T130728Z-2b7815d4c850-transformer-temperature-calibration-1.0.0.json
```

The command verifies every source report, split manifest, retained model, and
calibration artifact before querying the benchmark workload. It forces offline
Hugging Face loading and hides the GPU from both candidate subprocesses.

The closed aggregate report is written beneath
`data/evaluations/cfpb/model-selection/`. An identical replay validates and
returns that report without rerunning the benchmark. Changed source bytes,
artifacts, workload, environment identity, or prediction contracts fail closed.

## Current evidence status

The utility rule is accepted and the implementation is awaiting its clean-commit
real run. No CT-306 timing, memory result, or operational candidate is accepted
until that report is reviewed.
