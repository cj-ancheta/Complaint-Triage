# Required continuous-integration profiles

Status: QA-103 locally verified; required remote run pending

The CI workflow has two independent Linux x86-64 jobs. Both install only
hash-enforced third-party locks, install reviewed Git source with dependency
resolution and build isolation disabled, run against a disposable PostgreSQL
service, and produce separate coverage reports.

## Standard job

The `standard` job uses Python 3.13 and
`requirements/locks/standard-py313-linux-x86_64.lock.txt`. It runs Ruff,
formatting, and the complete standard test suite. Transformer-only tests skip
when their explicitly required stack is absent.

## CPU transformer job

The `transformer-cpu` job uses Python 3.12 and installs, in order:

1. the shared bootstrap lock;
2. `transformer-py312-linux-x86_64.lock.txt` from PyPI;
3. `torch-cpu-py312-linux-x86_64.lock.txt` from the official PyTorch CPU index
   with `--no-deps`; and
4. the reviewed local project with `--no-deps --no-build-isolation`.

`HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` prevent model downloads. The
contract test uses only synthetic token IDs and tensors. It checks the exact
Torch/Transformers/Tokenizers/Safetensors identities, CPU-only execution,
Transformers collation, deterministic tensor computation, and a safetensors
round trip.

## GPU separation

True CUDA integration is marked `gpu`. Ordinary pull-request CI runs
`pytest -m "not gpu"`; it must not install the 1.92 GB CUDA wheel or claim GPU
acceptance. GPU verification remains an explicit local acceptance procedure
using the Windows CUDA lock and a compatible device.

## Data and network boundaries

Neither job downloads the CFPB corpus, reads local model artifacts, contacts the
Hugging Face Hub, or accesses the frozen test partition for modeling. Tests use
committed aggregate evidence, deterministic fixtures, temporary files, and the
disposable PostgreSQL service. Secrets beyond the job-local disposable database
credential are neither required nor authorized.

## Local Linux replay

QA-103 generated and replayed the Linux locks inside matching official Python
containers while overlaying `data/raw`, `artifacts`, and `data/model_cache` with
empty read-only filesystems. Results were:

- Python 3.13 standard: 293 passed, four expected skips, five existing
  joblib/NumPy warnings;
- Python 3.12 CPU transformer: 294 passed, two expected skips, one GPU test
  deselected, five existing warnings; and
- `pip check` and target-platform `pip-audit 2.10.1` passed for both profiles.

QA-CI-001 closes only after both jobs pass on GitHub Actions. A local container
run proves the implementation and lock compatibility but cannot prove the
remote required-check configuration.
