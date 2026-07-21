# Architecture

## Phase 0 decision

The project is separated into two repositories:

```text
complaint-triage-ml
  Python ingestion, SQL, model training, evaluation, FastAPI, and governance

complaint-triage-web
  Lovable-generated React and TypeScript interface
```

The frontend will consume a versioned HTTP contract. It will not train or host the PyTorch model, and it will not contain server-side secrets.

## Planned backend flow

```text
CFPB API/export
  -> bounded Python ingestion
  -> immutable local raw batches and manifest
  -> PostgreSQL raw/staging/analytical layers
  -> temporal feature and split pipeline
  -> baseline and transformer candidates
  -> calibration and abstention evaluation
  -> versioned model artifact
  -> FastAPI service
  -> Lovable web application
```

This is a planned architecture, not a claim that the components already exist.

## Current implemented boundary

Only the installable Python package, documentation, validation configuration, and smoke test exist in Phase 0.

## Architecture decisions

- [ADR 0001: Separate ML backend and Lovable frontend](decisions/0001-separate-backend-and-frontend.md)
- [ADR 0002: Standard Python environment for Phase 0](decisions/0002-standard-python-environment.md)

