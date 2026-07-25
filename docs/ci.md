# Required continuous-integration profiles

Status: QA-103 and QA-105 accepted; runtime and security gates remotely passed

The CI workflow has two independent Linux x86-64 runtime jobs. Both install only
hash-enforced third-party locks, install reviewed Git source with dependency
resolution and build isolation disabled, run against a disposable PostgreSQL
service, audit their installed dependencies, validate separate CycloneDX SBOMs,
and produce separate coverage reports. A third `security` job scans Git history
and the hardened database image.

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

GitHub Actions run
[`30161131645`](https://github.com/cj-ancheta/Complaint-Triage/actions/runs/30161131645)
passed both `standard` and `transformer-cpu` on commit
`3c37677e08711697de6a89fde5b59231fef377b3`. Together with the local container
replays, that closes QA-CI-001. QA-104 separately controls whether those job
names are mandatory before `main` changes.

## QA-105 security profile

All third-party Actions are pinned to immutable commits. Gitleaks scans complete
history with redaction and proves a controlled ephemeral fixture is rejected.
Both runtime jobs install a separate hash-locked `pip-audit` tool profile, fail
on actionable installed-package advisories, and validate privacy-bounded
CycloneDX JSON. The security job builds the digest-pinned, upgraded PostgreSQL
wrapper and fails Trivy on actionable HIGH or CRITICAL findings. See
[`security_supply_chain.md`](security_supply_chain.md) for exception expiry,
update, and local-replay rules.

GitHub Actions run
[`30162536790`](https://github.com/cj-ancheta/Complaint-Triage/actions/runs/30162536790)
passed `standard`, `transformer-cpu`, and `security` on commit
`41daa8b16861b5dad9ef71ff0dd78fe7c6dac2cc`. Protected `main` now requires all
three exact contexts in strict mode.

## QA-106 coverage and warning ratchet

The standard and transformer jobs each fail below 69% combined statement/branch
coverage, but enforce the floor independently against separate reports. The
initial floor sits below the demonstrated 69.36% Windows standard and 69.02%
Linux CPU-transformer results so platform variation does not create a false
gate, while any material regression fails. The local CUDA-capable transformer
suite reaches 70.74%; its GPU-only path is intentionally absent from ordinary
CPU CI. Raising one profile's floor does not lower the other.

Pytest treats every unexpected warning as an error. The only acknowledged
exception is the exact joblib `numpy_pickle` shape-assignment deprecation
triggered by NumPy 2.5 during the governed local artifact round trip. The
scikit-learn LogisticRegression penalty warning was removed by expressing L2
regularization through `l1_ratio=0.0`. Dependency review should remove the
joblib exception once the locked stack no longer emits it.

GitHub Actions run
[`30163081497`](https://github.com/cj-ancheta/Complaint-Triage/actions/runs/30163081497)
passes both independent floors plus `security` on commit
`8250f5ce12b6198f979272edae6bb5ab508d9716`.

## QA-107 schema-drift profile

Each runtime job upgrades an empty disposable PostgreSQL database through all
four revisions and runs `alembic check` against the authoritative eight-table
SQLAlchemy metadata with all governed schemas included. This gate executes
before the test suite, so a model change without a migration—or a migration not
represented by the model—blocks the profile. PostgreSQL functions and triggers
remain protected by their behavioral integration tests because they are outside
Alembic's ordinary table autogeneration scope. See
[`database_schema_drift.md`](database_schema_drift.md).
