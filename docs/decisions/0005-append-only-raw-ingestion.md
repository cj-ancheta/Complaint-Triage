# ADR 0005: Append-only raw ingestion through validated manifests

- Status: Accepted
- Date: 2026-07-22
- Decision owners: Charles Jr Ancheta and project maintainer
- Scope: the first PostgreSQL raw-layer migration and loader

## Context

ADR 0003 defines one CFPB response as immutable exact bytes plus a safe,
versioned manifest. ADR 0004 supplies a local PostgreSQL service but deliberately
creates no application tables. CT-106 must connect these contracts while proving
reconciliation, idempotency, and recoverability without acquiring or retaining
real complaint data.

Raw responses can contain public complaint narratives. A loader must therefore
fail before writing when lineage does not reconcile and must not echo source
values in success output, controlled errors, or normal logs. The real-data
retention policy remains unresolved and is a project phase-gate decision.

## Decision

Use these responsibilities:

- Alembic owns ordered PostgreSQL schema changes.
- SQLAlchemy supplies Alembic's database engine and safe URL construction.
- Psycopg performs the small, explicit transactional insert path.
- `jsonschema` validates every manifest against the existing Draft 2020-12
  contract at runtime.

Create two tables in a dedicated `raw` schema:

- `raw.ingestion_batches` stores one safe manifest, its request and artifact
  identities, retrieval time, retention marker, and reconciled row counts.
- `raw.complaints` stores source-aligned JSONB, complaint ID, stable source-row
  ordinal, batch lineage, and a canonical per-record SHA-256.

The loader validates, in order:

1. controlled manifest location and closed JSON Schema;
2. the synthetic-only retention boundary;
3. artifact containment, exact-byte size, SHA-256, and content address;
4. canonical request fingerprint and deterministic batch ID;
5. response envelope, metadata, row aggregates, dates, IDs, and observed fields;
6. explicit synthetic markers that reduce accidental mislabelling of real data.

Only then does it open a database transaction. The batch insert uses its stable
identity as the idempotency boundary. A replay with the same batch, request, and
artifact returns `already_ingested` and inserts zero rows. Any conflict or row
failure rolls back the entire batch.

Database triggers reject `UPDATE` and `DELETE` on both raw tables. Removal is an
explicit migration/retention operation, not an ordinary application mutation.

Real manifests are unconditionally rejected in CT-106. No environment flag can
silently select a retention policy. Enabling real data requires a separately
approved policy and a bounded follow-up change.

## Dependency rationale

- Alembic `>=1.18.5,<1.19`: plain SQL files do not provide ordered revision
  history, upgrade state, or a standard downgrade path.
- SQLAlchemy `>=2.0.51,<2.1`: Alembic uses its PostgreSQL engine and its URL type
  prevents unsafe manual credential interpolation.
- Psycopg binary `>=3.3.4,<3.4`: the standard library has no PostgreSQL protocol
  driver; Psycopg provides transactions, bound parameters, and JSONB adapters.
- `jsonschema >=4.23,<5` moves into runtime dependencies because manifest
  validation is now production behavior rather than test-only contract checking.

All ranges stay within one compatible minor or major line. A future dependency
locking issue should add exact transitive resolution for clean-checkout builds.

## Consequences

Benefits:

- altered bytes and drifting manifests fail before database access;
- a batch is either fully present or absent;
- reruns are safe and observable;
- raw history cannot be casually rewritten;
- source schema remains available without prematurely normalizing it;
- CI proves behavior against a real disposable PostgreSQL database.

Costs and limits:

- JSONB duplicates the ignored raw artifact and consumes local database storage;
- append-only triggers make corrections explicit rather than convenient;
- database-owner credentials can still bypass controls by changing schema;
- synthetic markers prevent common mistakes but cannot defeat intentional
  falsification;
- no real CFPB batch can be loaded until retention is approved;
- the local initialization role is not a production least-privilege design.

## Alternatives considered

### SQLAlchemy ORM for row loading

Rejected for this slice. Two fixed inserts are clearer as parameterized SQL and
do not need identity maps or domain entities. SQLAlchemy remains appropriate for
migration connectivity.

### Store only normalized raw columns

Rejected. Normalizing during raw ingestion would erase the source-aligned record
needed to reproduce later staging decisions and detect additive fields.

### Upsert raw rows

Rejected. Updating an earlier payload would weaken lineage and make a batch cease
to represent the exact acquired artifact.

### Permit real data when an environment variable matches the manifest

Rejected for CT-106. A matching string is not a retention policy and would let an
operator bypass the unresolved governance decision.

## Acceptance evidence

Accept this ADR when review confirms that:

- unit tests reject unsafe paths, changed bytes, drifted aggregates, and real
  manifests;
- a disposable PostgreSQL test proves rollback, one-time insertion, replay,
  reconciliation, and append-only triggers;
- CLI output contains identifiers and counts but no source row values;
- CI runs the PostgreSQL test; and
- the documented migration and synthetic rehearsal commands work.
