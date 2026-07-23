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

The repository includes the controlled CFPB source profiler, raw batch manifest
contract, local PostgreSQL Compose service, and exact-byte raw loader. The
loader atomically inserts `raw.ingestion_batches` and `raw.complaints`, and
database triggers enforce append-only behavior. ADR 0009 approves bounded local
retention, and CT-108 enforces it at the manifest boundary. CT-109 adds the fixed
16-month partition, preflight-count enforcement, run-scoped streamed hashing,
iterative JSON inspection, atomic publication, and verified cleanup workflow.
CT-110 adds the gated live adapter and reconciles the accepted retained run
without exposing source rows in commit-safe evidence.

The accepted CT-107 staging layer adds versioned, append-only transformation
batches and one accepted or quarantined outcome per raw row. ADR 0007 fixes the
current-form identity taxonomy and pre-2025 window. The accepted CT-202 analytical
layer records one versioned eligibility outcome per staged row without copying
narratives. Accepted ADR 0010 fixes whole-month train, validation, and test
boundaries plus a normalized SHA-256 duplicate rule. CT-203 adds append-only
split runs and outcomes without copying narratives or complaint identifiers;
the accepted first real split reconciles with zero included fingerprint overlap.
CT-204 evaluates a constant training-majority reference directly from the
commit-safe split counts; its first aggregate report is accepted as issue
evidence. Accepted ADR 0011 fixes CT-205's train-only TF-IDF vocabulary,
four-candidate sparse logistic search, validation-only selection rule, and
local-only fitted-artifact boundary. The real run selected the converged
unweighted `C=1.0` candidate and retained its governed pipeline locally; the
aggregate validation evidence is awaiting acceptance and test remains untouched.

## Architecture decisions

- [ADR 0001: Separate ML backend and Lovable frontend](decisions/0001-separate-backend-and-frontend.md)
- [ADR 0002: Standard Python environment for Phase 0](decisions/0002-standard-python-environment.md)
- [ADR 0003: Content-address raw CFPB batches](decisions/0003-content-addressed-raw-batches.md)
- [ADR 0004: Local PostgreSQL with Docker Compose](decisions/0004-local-postgresql-compose.md)
- [ADR 0005: Append-only raw ingestion through validated manifests](decisions/0005-append-only-raw-ingestion.md)
- [ADR 0006: Versioned staging outcomes with explicit quarantine reasons](decisions/0006-versioned-staging-outcomes.md)
- [ADR 0007: Current-form product taxonomy and pre-2025 window](decisions/0007-proposed-taxonomy-window.md)
- [ADR 0008: Analytical population and exclusions](decisions/0008-proposed-analytical-population.md)
- [ADR 0009: Local-only 120-day real-data retention](decisions/0009-local-real-data-retention.md)
- [ADR 0010: Temporal split and normalized duplicate isolation](decisions/0010-temporal-split-duplicate-isolation.md)
- [ADR 0011: Validation-only TF-IDF logistic-regression selection](decisions/0011-tfidf-logreg-validation-selection.md)
