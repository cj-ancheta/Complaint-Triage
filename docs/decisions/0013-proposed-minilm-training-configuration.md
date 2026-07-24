# ADR 0013: Proposed MiniLM training configuration

- Status: Accepted
- Date: 2026-07-24
- Decision owner: Charles Jr Ancheta
- Scope: CT-303 compact-transformer training and validation selection

## Context

CT-301 accepts the immutable `microsoft/MiniLM-L12-H384-uncased` revision and a
384-token maximum. CT-302 provides deterministic, single-process train and
validation streams with length-grouped dynamic padding. The accepted split has
394,564 training rows, 80,992 validation rows, and 85,786 frozen test rows.

The local NVIDIA GeForce RTX 5060 Laptop GPU reports 8,151 MiB VRAM, driver
596.36, and compute capability 12.0. The isolated environment uses Python
3.12.10. On 2026-07-24, the official PyTorch CUDA 13.0 index exposes
`torch==2.13.0+cu130` for CPython 3.12 on Windows. Its wheel is 1,915,519,202
bytes (1.784 GiB) with SHA-256
`2efab1e83604ca628c6d85b9e188c153690980498d1297081a9dad704919303c`.

The training distribution is highly imbalanced. The largest class contains
248,062 rows and the rarest contains 1,173, a 211.48-to-1 ratio. CT-206 found a
large rare-versus-common validation macro-F1 gap for the sparse baseline, so
the transformer loss must address imbalance without duplicating rare rows.

## Proposed dependencies

Add only `torch==2.13.0+cu130` from the official CUDA 13.0 wheel index to the
ignored Python 3.12 transformer environment. Install with `--no-cache-dir` so
the 1.784 GiB wheel is not retained in the pip cache. Keep Transformers 5.14.1,
Tokenizers 0.22.2, Hugging Face Hub 1.24.0, and Safetensors 0.8.0 pinned as in
CT-301.

Do not add Accelerate or MLflow for this bounded issue. PyTorch AMP and the
existing framework-neutral dataset pipeline are sufficient for one custom
single-GPU training loop. Full MLflow 3.14.0 pulls in Arrow, plotting, Docker,
web-server, and model-serialization packages; `mlflow-skinny` still introduces
telemetry, cloud-SDK, FastAPI, and authentication dependencies. A closed,
versioned JSON experiment report plus hashed local checkpoints already records
code, data, configuration, epoch metrics, software, hardware, and artifact
lineage. Reconsider MLflow only if later work needs multiple recurring
experiments or a tracking server.

## Model and input

- Load `AutoModelForSequenceClassification` from immutable revision
  `9a201d7b3ebebc5feabf9fbb4b3a4ec5d3f2440d` with
  `use_safetensors=True`, `trust_remote_code=False`, and eleven labels.
- Reject a resolved revision mismatch.
- Fine-tune all MiniLM parameters; do not freeze encoder layers.
- Use narrative text only through the accepted CT-302 pipeline.
- Use maximum length 384, length-grouped dynamic padding, and label IDs 0–10.
- Do not read or score test rows.

## Loss and class imbalance

Use one moderated square-root-balanced cross-entropy loss. For training class
count `n_c`, total `N=394,564`, and `K=11` classes:

```text
weight_c = sqrt(N / (K * n_c))
```

Representative weights are 0.3803 for the majority credit-reporting class,
1.1421 for checking/savings, 3.0603 for prepaid card, and 5.5299 for the rarest
debt-or-credit-management class. Full inverse-frequency balancing would assign
the rarest class 30.5792 and is rejected as too aggressive for the first deep
candidate.

Do not oversample or duplicate rows. The square-root rule is fixed from
training counts before model fitting and cannot change in response to
validation metrics. This choice prioritizes macro F1 and rare-class learning
while moderating the variance and overfitting risk of full inverse weighting.

## Optimization

| Parameter | Proposed value |
|---|---|
| optimizer | PyTorch `AdamW`, non-fused |
| learning rate | `2e-5` |
| weight decay | `0.01` |
| Adam betas | `(0.9, 0.999)` |
| Adam epsilon | `1e-8` |
| scheduler | linear decay |
| warmup | 6% of optimizer steps |
| maximum epochs | 3 |
| gradient clipping | L2 norm `1.0` |
| dropout | upstream MiniLM defaults |
| base random seed | 42 |
| validation frequency | end of each completed epoch |

Use CUDA FP16 automatic mixed precision with `torch.amp.autocast` and
`GradScaler`. FP16 is preferred over automatically switching precision modes
because one declared numerical path is easier to reproduce and explain.

## Batch-size smoke and fallback

Keep effective batch size 32. Before real-data training, run a maximum-length
synthetic forward/backward hardware smoke in this fixed order:

| Priority | Per-device batch | Gradient accumulation | Gradient checkpointing |
|---:|---:|---:|---|
| 1 | 16 | 2 | off |
| 2 | 8 | 4 | off |
| 3 | 4 | 8 | on |

Select the first configuration that completes the declared smoke without CUDA
out-of-memory or non-finite loss. Clear CUDA state between failed attempts and
record the selected configuration. This selection uses hardware feasibility
only, not validation quality, and therefore does not tune the model against the
validation set. Fail closed if the third configuration cannot run.

After the synthetic memory smoke, run a training-only integration smoke on a
fixed 100 rows per class for 20 optimizer steps. It writes no model artifact,
experiment report, or performance claim.

## Reproducibility controls

- Seed Python, NumPy, PyTorch CPU, and every CUDA device with 42.
- Set `CUBLAS_WORKSPACE_CONFIG=:4096:8` before CUDA initialization.
- Disable cuDNN benchmarking and enable deterministic algorithms.
- Use the CT-302 single-process stream; data-loader workers remain zero.
- Use epoch seed `42 + epoch` for training order and fixed validation order.
- Record driver, GPU, CUDA runtime, PyTorch, Transformers, tokenizer, and Python
  versions.
- Treat reproducibility as best effort across the recorded software/hardware
  boundary; do not promise bitwise equality across drivers or GPU generations.

## Early stopping and epoch selection

Evaluate aggregate validation metrics after each full epoch. A completed epoch
is eligible only when training and validation loss are finite and all counts
reconcile.

Use unrounded validation macro F1 as the monitored metric with minimum
improvement `0.001` and patience one completed epoch. Stop after the first
eligible epoch that fails to improve the best macro F1 by at least `0.001`, or
after epoch three.

Select the retained epoch using this ordered rule:

1. highest validation macro F1;
2. highest validation worst-class recall;
3. highest validation weighted F1; and
4. earlier epoch.

This is one fixed transformer candidate, not a learning-rate or loss-function
search. Report accuracy, macro F1, weighted F1, worst-class recall, per-class
precision/recall/F1, top-2 accuracy, confusion matrix, and epoch losses. Leave
calibration to CT-305 and baseline-versus-transformer utility selection to
CT-304/CT-306.

## Checkpoints, tracking, and privacy

Store checkpoints only under ignored
`artifacts/cfpb/transformer/<run-id>/`. Save model weights with safetensors.
For interruption recovery, a trusted local checkpoint may contain optimizer,
scheduler, scaler, step, and RNG state; never load such state from an external
or unverified path. Keep only the best model and latest resumable checkpoint.

Hash retained artifacts and record their relative paths, byte counts, and
local-only retention boundary. Model weights, optimizer state, tokenizer cache,
and the local experiment store remain untracked and governed by ADR 0009.

The commit-safe report may contain configuration, counts, aggregate metrics,
timings, memory peaks, hardware/software versions, artifact hashes, and safe
failure codes. It must not contain narratives, complaint IDs, token IDs,
vocabulary, row identities, per-row predictions, or local absolute paths. It
must keep `portfolio_promotion_approved=false` and `test_accessed=false`.

## Storage and runtime consequences

The PyTorch wheel download is 1.784 GiB; the installed environment and CUDA
libraries will consume more. The model safetensors file is approximately 133
MB, and local optimizer/resume state can be several times the model size. The
machine currently has 116.73 GiB free on `E:`. Installation and checkpoint
retention therefore fit locally, but the use of `--no-cache-dir` and the
best-plus-latest limit prevent avoidable duplication.

Full runtime is intentionally not claimed before the smoke benchmark. The
accepted dataset contains 394,564 rows, so even one epoch is substantial on a
laptop GPU.

## Approval

Charles explicitly approved PyTorch 2.13.0 CUDA 13.0 as the only new
dependency, moderated square-root-balanced loss, fixed optimization and FP16
configuration, the effective-batch-32 hardware fallback ladder, three-epoch
maximum and macro-F1 early stopping rule, JSON-plus-hashed-artifact tracking
instead of MLflow, and the local trusted resume-checkpoint boundary on
2026-07-24.

## Primary references

- PyTorch CUDA 13.0 wheel index:
  <https://download.pytorch.org/whl/cu130/torch/>
- PyTorch installation guidance:
  <https://docs.pytorch.org/get-started/locally/>
- PyTorch reproducibility notes:
  <https://docs.pytorch.org/docs/stable/notes/randomness.html>
- PyTorch automatic mixed-precision examples:
  <https://docs.pytorch.org/docs/stable/notes/amp_examples.html>
- Microsoft MiniLM model card:
  <https://huggingface.co/microsoft/MiniLM-L12-H384-uncased>
- Pinned MiniLM revision:
  <https://huggingface.co/microsoft/MiniLM-L12-H384-uncased/tree/9a201d7b3ebebc5feabf9fbb4b3a4ec5d3f2440d>
- Hugging Face model loading API:
  <https://huggingface.co/docs/transformers/main_classes/model>
- MLflow tracking documentation (evaluated and deferred):
  <https://mlflow.org/docs/latest/ml/tracking/>
