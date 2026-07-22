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

The repository now includes the controlled CFPB source profiler, raw batch
manifest contract, local PostgreSQL Compose service, first Alembic migration, and
a proposed synthetic-only raw loader. The loader validates exact bytes and
lineage before atomically inserting `raw.ingestion_batches` and
`raw.complaints`. Database triggers enforce append-only behavior. Real-data
loading is blocked until a retention policy is separately approved.

## Architecture decisions

- [ADR 0001: Separate ML backend and Lovable frontend](decisions/0001-separate-backend-and-frontend.md)
- [ADR 0002: Standard Python environment for Phase 0](decisions/0002-standard-python-environment.md)
- [ADR 0003: Content-address raw CFPB batches](decisions/0003-content-addressed-raw-batches.md)
- [ADR 0004: Local PostgreSQL with Docker Compose](decisions/0004-local-postgresql-compose.md)
- [ADR 0005: Append-only raw ingestion through validated manifests](decisions/0005-append-only-raw-ingestion.md)
