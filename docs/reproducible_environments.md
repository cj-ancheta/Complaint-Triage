# Reproducible local environments

Status: QA-102 Windows profiles accepted; QA-103 Linux profiles locally
verified with remote-CI acceptance pending  
Decision: [ADR 0017](decisions/0017-pip-compatible-hashed-locks.md)

## Trust model

The lock files protect third-party packages. The reviewed Git commit protects
the local project source. Install locked dependencies first, then install the
project with both dependency resolution and build isolation disabled.

Use these commands from the repository root. Do not add `--upgrade`, remove
`--require-hashes`, combine the PyPI and CUDA locks, or install the CUDA lock
without `--no-deps`.

## Standard Python 3.13 environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/locks/bootstrap.lock.txt
.\.venv\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/locks/standard-py313-win-amd64.lock.txt
.\.venv\Scripts\python.exe -m pip install `
  --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
```

## Transformer Python 3.12 environment

The CUDA wheel is approximately 1.92 GB. Its Python-side dependencies are in
the PyPI transformer lock; the CUDA step installs exactly one hash-checked wheel
and cannot resolve dependencies.

```powershell
py -3.12 -m venv .venv-transformer
.\.venv-transformer\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/locks/bootstrap.lock.txt
.\.venv-transformer\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/locks/transformer-py312-win-amd64.lock.txt
.\.venv-transformer\Scripts\python.exe -m pip install `
  --require-hashes --no-deps `
  -r requirements/locks/torch-cu130-py312-win-amd64.lock.txt
.\.venv-transformer\Scripts\python.exe -m pip install `
  --no-deps --no-build-isolation -e .
.\.venv-transformer\Scripts\python.exe -m pip check
```

Verify the exact stack:

```powershell
.\.venv-transformer\Scripts\python.exe -c `
  "import torch, transformers, tokenizers, safetensors; print(torch.__version__, transformers.__version__, tokenizers.__version__, safetensors.__version__)"
```

Expected locked identities are `2.13.0+cu130`, `5.14.1`, `0.22.2`, and `0.8.0`.

## Linux CI environments

GitHub Actions uses the platform-matched standard and transformer locks rather
than either Windows file. The transformer job installs the isolated CPU wheel:

```bash
python -m pip install --require-hashes -r requirements/locks/bootstrap.lock.txt
python -m pip install --require-hashes \
  -r requirements/locks/transformer-py312-linux-x86_64.lock.txt
python -m pip install --require-hashes --no-deps \
  -r requirements/locks/torch-cpu-py312-linux-x86_64.lock.txt
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check
```

The standard job substitutes
`requirements/locks/standard-py313-linux-x86_64.lock.txt` and does not install
Torch. See [the CI profile guide](ci.md) for offline and GPU boundaries.

## Run the evidence checks

Start the disposable/local PostgreSQL service, then run both suites:

```powershell
$env:RUN_POSTGRES_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv-transformer\Scripts\python.exe -m pytest -q
```

The final QA-102 clean-replay result was 293 passed plus one expected torch-only
skip in the standard environment and 294 passed in the transformer environment.
Five existing joblib/NumPy deprecation warnings remain QA-WARN-001.

## Regenerate locks

Create separate disposable compiler environments so each lock is resolved by
its target Python version. Install the same pinned compiler tool in both:

```powershell
py -3.13 -m venv .venv-lock
.\.venv-lock\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/locks/bootstrap.lock.txt
.\.venv-lock\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/locks/lock-tool.lock.txt
py -3.12 -m venv .venv-lock-transformer
.\.venv-lock-transformer\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/locks/bootstrap.lock.txt
.\.venv-lock-transformer\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/locks/lock-tool.lock.txt
```

Compile the standard lock with Python 3.13:

```powershell
.\.venv-lock\Scripts\python.exe -m piptools compile pyproject.toml `
  --extra dev --generate-hashes --allow-unsafe --strip-extras `
  --resolver backtracking `
  --output-file requirements/locks/standard-py313-win-amd64.lock.txt
```

Compile the transformer PyPI lock with the isolated Python 3.12 compiler:

```powershell
.\.venv-lock-transformer\Scripts\python.exe -m piptools compile `
  pyproject.toml requirements/transformer-py312.in `
  --extra dev --generate-hashes --allow-unsafe --strip-extras `
  --resolver backtracking `
  --output-file requirements/locks/transformer-py312-win-amd64.lock.txt
```

Generate the Linux files only inside matching Linux x86-64 Python 3.13 and 3.12
environments. Use the same `piptools compile` arguments and the Linux output
filenames. Do not cross-audit a Linux lock on Windows: environment markers can
legitimately require different transitive packages. The CPU Torch lock is
reviewed manually against the official PyTorch CPU index, just like the CUDA
lock.

Regenerate the bootstrap and lock-tool locks only when intentionally changing
their `.in` files. The CUDA lock is reviewed manually against PyTorch's official
index; never let the CUDA index resolve the PyPI dependency graph.

After regeneration, review the diff, run the QA lock-contract test, audit both
environments, and repeat both clean-install suites before acceptance.
