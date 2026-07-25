# Incremental static type checking

Status: QA-108 accepted; GitHub Actions run 30164122886 passed

Mypy 2.3.0 runs in strict mode under the repository's Python 3.12 compatibility
floor. The first protected scope is deliberately small and meaningful:

- database environment parsing and URL construction;
- security/SBOM completion and its fail-closed identity boundary;
- authoritative SQLAlchemy database metadata; and
- the immutable product taxonomy; and
- the dependency-free retention policy and aggregate-only deadline checkpoint.

These modules are shared control surfaces with stable interfaces and no ignored
errors. The scope is listed explicitly in `pyproject.toml`; changing it is a
reviewable policy change. Do not use global `ignore_missing_imports`, per-module
blanket suppression, or untyped escape hatches to make a wider scope appear
clean.

Both Linux runtime profiles install Mypy from a matching Python-version,
hash-enforced tool lock and run the same configuration. This checks Python 3.12
syntax/type compatibility even in the Python 3.13 standard job. Add modules in
small groups after resolving their real errors and third-party stub decisions;
never remove a protected module merely to pass CI.

## Local verification

Install the reviewed type-tool lock into a disposable environment containing
the project dependencies, then run:

```powershell
.\.venv-type\Scripts\python.exe -m mypy
```

Expected output is `Success: no issues found in 6 source files`. The disposable
`.venv-type` directory is ignored local tooling, not repository evidence.

GitHub Actions run
[`30164122886`](https://github.com/cj-ancheta/Complaint-Triage/actions/runs/30164122886)
passes both strict Mypy steps plus `security` on commit
`6356d2db604e7580fcb39453233743ec48668394`.
