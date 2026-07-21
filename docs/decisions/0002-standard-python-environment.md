# ADR 0002: Use Standard Python Environment for Phase 0

- Status: accepted
- Date: 2026-07-21

## Context

The local machine has Python 3.13 but does not have `uv`. Phase 0 needs a reproducible environment without adding a global dependency merely for scaffolding.

## Decision

Use:

- `pyproject.toml` as project metadata;
- Python 3.13 locally;
- standard `venv` for isolation;
- `pip install -e ".[dev]"` for editable development installation;
- a declared compatibility range of Python 3.12 through 3.13.

## Consequences

- setup works with installed tooling;
- dependencies remain declared in one project file;
- no lock file is produced during Phase 0;
- reproducible transitive resolution is weaker than a locked workflow.

## Revisit trigger

Before significant data-science dependencies are added, compare `uv`, Poetry, and a pip-compatible lock workflow. Record any change in a new ADR rather than silently replacing the environment.

