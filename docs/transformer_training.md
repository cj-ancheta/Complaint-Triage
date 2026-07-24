# MiniLM training and validation selection

CT-303 fits one compact transformer candidate under the accepted ADR 0013
configuration. It does not search model families, learning rates, loss rules,
or batch sizes using validation quality. The test split remains frozen.

## What is fixed

- `microsoft/MiniLM-L12-H384-uncased` at immutable revision
  `9a201d7b3ebebc5feabf9fbb4b3a4ec5d3f2440d`;
- narrative-only inputs, eleven accepted labels, and maximum length 384;
- square-root-balanced cross-entropy weights derived once from training counts;
- AdamW at `2e-5`, weight decay `0.01`, 6% linear warmup, FP16, and gradient
  clipping at 1.0;
- effective batch size 32 using the first hardware-feasible approved batch
  configuration;
- at most three epochs; and
- validation macro-F1 early stopping with minimum improvement 0.001 and patience
  one completed epoch.

The retained epoch is ordered by validation macro-F1, worst-class recall,
weighted-F1, and then earlier epoch. Calibration, abstention, final test use,
and baseline-versus-transformer promotion are later governed issues.

## Commands

Run the non-persistent hardware and training-only smoke first:

```powershell
.\.venv-transformer\Scripts\complaint-triage.exe `
  smoke-transformer-training `
  --split-manifest `
  data/manifests/cfpb/splits/cfpb-run-20260722T130728Z-2b7815d4c850-split-1.0.0.json
```

After the smoke gate and explicit approval, run the full validation-only fit
from a clean implementation commit:

```powershell
.\.venv-transformer\Scripts\complaint-triage.exe `
  train-transformer `
  --split-manifest `
  data/manifests/cfpb/splits/cfpb-run-20260722T130728Z-2b7815d4c850-split-1.0.0.json
```

Progress events contain only epoch numbers, aggregate counts, timings, and
validation metrics. They never contain narratives, row identities, or token
arrays.

## Evidence and artifacts

The commit-safe report is written under
`data/evaluations/cfpb/transformer/`. Its closed JSON Schema is
`contracts/cfpb-transformer-training.schema.json`. It records the split hash,
implementation commit, fixed configuration, aggregate epoch metrics, runtime,
hardware and software versions, artifact hashes, and explicit privacy and
claim boundaries.

Local artifacts are ignored by Git under
`artifacts/cfpb/transformer/<run-id>/`:

- `best-model.safetensors`: weights for the selected validation epoch;
- `latest-model-epoch-<n>.safetensors`: latest completed epoch weights;
- `latest-training-state-epoch-<n>.pt`: trusted-local optimizer, scheduler,
  scaler, RNG, and aggregate history state; and
- `latest-resume.json`: identity and SHA-256 checks for the resumable pair.

The resumable `.pt` file is never a deployable or externally trusted artifact.
It is loaded only from the exact ignored project directory after its hash,
split, commit, class weights, and batch configuration reconcile. A new epoch
generation becomes active only after its manifest is atomically replaced; the
older generation is pruned afterward. An interruption therefore leaves either
the old generation or the new generation verifiable.

## What to understand for an interview

Class weighting changes the loss contribution of rare classes without copying
rows. Macro-F1 gives every class equal importance, while weighted-F1 reflects
the operational class mix and worst-class recall exposes the weakest routing
category. Early stopping controls additional fitting, whereas the ordered
selection rule decides which fully evaluated epoch is retained. Neither rule
uses the frozen test set.

Validation metrics are still tuning evidence. They cannot yet be promoted to
the README, portfolio, or resume and do not prove that MiniLM has better
operational utility than the TF-IDF baseline.

## First full-fit evidence

The authoritative validation-only run uses implementation commit
`2669e5bc05ffdbdb3d2779478851f7fe2913072a`. All three epochs reconciled
394,564 training rows and 80,992 validation rows. The test split was never
queried. Epoch 3 was retained because each epoch improved validation macro-F1
by more than the fixed 0.001 boundary.

| Epoch | Train loss | Validation loss | Accuracy | Macro-F1 | Weighted-F1 | Worst recall | Top-2 accuracy | Train seconds | Validation seconds |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.85123 | 0.59057 | 0.87136 | 0.68656 | 0.87339 | 0.00000 | 0.96109 | 1,656.278 | 120.521 |
| 2 | 0.52874 | 0.54480 | 0.87921 | 0.72162 | 0.88178 | 0.16300 | 0.96333 | 1,614.567 | 114.544 |
| 3 | 0.46151 | 0.53608 | 0.88585 | 0.73575 | 0.88669 | 0.20705 | 0.96795 | 1,667.727 | 119.095 |

The weakest epoch-3 class is `Debt or credit management`: support 227,
precision 0.41964, recall 0.20705, and F1 0.27729. This limitation is material
despite the much stronger aggregate and majority-class results. CT-304 must
compare this validation evidence with the baseline rather than assuming the
transformer wins, and CT-305 must assess calibration separately.

Summed epoch train-plus-validation compute time was 5,292.732 seconds
(88.212 minutes). Peak allocated CUDA memory was 1,908.24 MiB. The selected
127.30 MiB safetensors artifact has SHA-256
`c83f4ad8c225dea2a8b32424d9af6179ee028dc6adf6bc1eeea9f18932325415`.
The closed report, idempotent replay, all retained artifact hashes, safetensors
metadata, and ignored-artifact boundary were independently revalidated after
the GPU released all memory.

These are validation-selection results only. The report keeps
`portfolio_promotion_approved=false`; no README, portfolio, resume, calibration,
abstention, or final-test claim is authorized by CT-303.

