# ADR 0017: Pip-compatible platform locks with enforced hashes

- Status: Accepted
- Date: 2026-07-25
- Decision owner: Charles Jr Ancheta
- Scope: QA-102 reproducible development and transformer environments

## Context

ADR 0002 chose `venv`, `pip`, and bounded dependency ranges while explicitly
deferring lock files. The repository QA found that accepted reports record
observed versions, but a fresh installation can resolve different transitive
packages. That is inadequate for a research artifact whose software environment
must be reconstructable independently.

The project has two local environments and two bounded Linux CI profiles:

- standard Windows AMD64, Python 3.13, for ingestion, database, sparse-model,
  governance, and ordinary tests; and
- transformer Windows AMD64, Python 3.12, with tokenizer dependencies from
  PyPI and a 1.92 GB CUDA 13.0 PyTorch wheel from PyTorch's separate index.
- standard Linux x86-64, Python 3.13, for the ordinary required CI job; and
- transformer Linux x86-64, Python 3.12, with the same Python-side transformer
  dependencies and a separate CPU-only PyTorch wheel.

Allowing the PyTorch index to resolve every dependency would blur the package
source boundary. Treating an editable local project as a hashed third-party
package would also be misleading: its identity is the reviewed Git commit, not
a PyPI artifact.

## Decision

Keep `pyproject.toml` as the human-edited direct-dependency policy and standard
`pip` as the installer. Add reviewed platform lock files generated with
`pip-tools==7.6.0`:

- `bootstrap.lock.txt` fixes pip, setuptools, wheel, and packaging;
- `standard-py313-{win-amd64,linux-x86_64}.lock.txt` fixes standard and
  development dependencies for each supported platform;
- `transformer-py312-{win-amd64,linux-x86_64}.lock.txt` fixes standard,
  development, tokenizer, and PyTorch Python-side dependencies from PyPI;
- `torch-cu130-py312-win-amd64.lock.txt` fixes exactly one CUDA wheel from the
  PyTorch index; and
- `torch-cpu-py312-linux-x86_64.lock.txt` fixes exactly one CPU wheel from the
  PyTorch index; and
- `lock-tool.lock.txt` fixes the lock-regeneration tool and its dependencies;
  and
- `audit-tool-py{312,313}-linux-x86_64.lock.txt` fixes the QA-105 audit/SBOM
  tool for each Linux runtime profile; and
- `type-tool-py{312,313}-linux-x86_64.lock.txt` fixes the QA-108 Mypy toolchain
  for each Linux runtime profile.

Every third-party installation uses `--require-hashes`. Install the local
project afterward with `--no-deps --no-build-isolation -e .`; this prevents the
editable build from resolving undeclared third-party packages and binds project
source to Git review. Install the CUDA wheel with `--no-deps` only after the
transformer PyPI lock, so its dependencies cannot be sourced from the CUDA
index.

The lock filenames are deliberately platform- and Python-specific. A lock must
be generated, installed, and audited on its named target; Windows and Linux
files are never treated as interchangeable.

## Integrity boundary

The CUDA wheel is
`torch-2.13.0+cu130-cp312-cp312-win_amd64.whl`. PyTorch's official index
publishes SHA-256
`2efab1e83604ca628c6d85b9e188c153690980498d1297081a9dad704919303c`,
which is enforced by the CUDA lock. The official response reports a
1,915,519,202-byte wheel; the clean replay downloaded and accepted it only
after the hash check.

Lock files contain package names, versions, source annotations, and hashes only.
They contain no credentials, complaint data, user paths, narratives, model
artifacts, or environment values.

## Regeneration policy

Regeneration is an explicit dependency-change review, not an automatic
formatting step:

1. start from a clean commit and a disposable lock-tool environment;
2. install `lock-tool.lock.txt` with `--require-hashes`;
3. compile the standard lock with Python 3.13 and transformer lock with Python
   3.12 using the commands in `docs/reproducible_environments.md`;
4. review every version and hash diff, including newly introduced transitives;
5. run vulnerability audit and both clean-install replays;
6. rerun the full PostgreSQL-backed suites; and
7. obtain owner review before accepting the new lock set.

Do not regenerate the CUDA lock from the combined dependency graph. Confirm its
exact wheel tag and digest against the official PyTorch index, then update the
single-wheel boundary explicitly.

## Consequences

Benefits:

- fresh Windows environments resolve identical third-party versions;
- hashes prevent silent package substitution;
- bootstrap and regeneration tooling are reproducible;
- PyPI and CUDA package-source boundaries remain separate; and
- accepted research evidence can cite an exact dependency manifest.

Costs and limitations:

- the lock files are large because they retain hashes for compatible published
  distributions;
- the 1.92 GB CUDA wheel makes a full clean replay expensive;
- Windows locks do not prove Linux CI reproducibility;
- every additional platform requires its own reviewed lock and replay;
- locks become stale and need vulnerability-aware review; and
- Git still authenticates local source, so repository protection remains an
  independent control.

## Verification evidence

QA-102 created disposable Windows environments from only the reviewed lock
files and local Git source:

- Python 3.13 standard: hashed bootstrap and dependency installs, `pip check`,
  editable no-dependency/no-isolation install, 293 passed and one expected
  torch-only skip;
- Python 3.12 transformer: hashed bootstrap, PyPI dependency, and isolated CUDA
  installs, `pip check`, exact stack import (`torch 2.13.0+cu130`,
  `transformers 5.14.1`, `tokenizers 0.22.2`, `safetensors 0.8.0`), and 292
  passed with no skips (294 tests).

Both replays used the disposable PostgreSQL integration boundary and did not
read, copy, or hash raw complaint data.
Both exact PyPI lock manifests also returned no known vulnerabilities when
audited with `pip-audit 2.10.1`; the separate non-PyPI CUDA wheel remains outside
that service's vulnerability database.

The replay also proved the failure boundary: an interrupted lock-generation
process temporarily replaced the CUDA lock with an incomplete file. The first
clean transformer replay then failed because Torch was absent. Restoring the
reviewed single-wheel lock and enforcing its digest made the next replay pass;
the repository lock-contract test now detects that truncation class directly.

## QA-103 Linux CI extension

QA-103 adds three exact-digest Linux x86-64 artifacts generated inside the
matching official Python containers: a Python 3.13 standard lock, a Python 3.12
transformer/PyPI lock, and an isolated `torch 2.13.0+cpu` lock. The official
PyTorch CPU index publishes SHA-256
`4ca4a9394b0c771238a4f73590fdbbc4debad85ed0fa63d026ae1b085da7d6e2`
for the CPython 3.12 manylinux 2.28 x86-64 wheel.

Fresh local Linux simulations installed the locks with hashes, passed
`pip check`, and ran the PostgreSQL-backed suites. The standard profile passed
293 tests with four expected platform/stack skips. The offline CPU transformer
profile passed 294 tests with two expected platform skips and one explicitly
deselected GPU acceptance test. It executed deterministic CPU tensor work,
Transformers collation, and a safetensors round trip without model downloads.
Both Linux PyPI lock manifests returned no known vulnerabilities when audited
inside their target platform with `pip-audit 2.10.1`.

This is local implementation evidence. QA-CI-001 remains open until the pushed
GitHub Actions `transformer-cpu` job succeeds remotely.

## Approval

Charles accepted the platform-specific, hash-enforced lock design and QA-102
evidence on 2026-07-25. This acceptance does not waive the separate remote-CI,
security-gate, or dependency-update review requirements.

## QA-105 audit-tool extension

QA-105 adds two target-Python Linux audit-tool locks generated from
`requirements/audit-tool.in`. They install `pip-audit==2.10.1` and its
CycloneDX dependencies with hashes after the runtime graph. Keeping the tooling
separate makes the runtime dependency intent reviewable while ensuring the
security gate itself is reproducible. The repository contract pins the exact
digest of all ten QA-105 lock artifacts. QA-108 later extends the repository
total to twelve with two target-Python type-tool locks.

## Rejected alternatives

### Continue with bounded ranges only

Rejected because it preserves time-dependent transitive resolution and leaves
QA-REPRO-001 open.

### Adopt Poetry or uv immediately

Rejected for this issue because neither is present, both would replace the
accepted environment workflow, and ordinary pip already supports enforced hash
installation. They can be reconsidered if multi-platform lock maintenance
becomes unmanageable.

### Resolve all packages through the CUDA index

Rejected because dependency confusion and source provenance become harder to
reason about. The CUDA index is authorized for one wheel only.

### Commit a frozen virtual environment

Rejected because environments are large, platform-specific binary trees rather
than reviewable source evidence.
