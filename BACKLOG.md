# Initial Implementation Backlog

This backlog converts `SPEC.md` into bounded delivery issues. Status values are `pending`, `in progress`, `review`, `complete`, or `blocked`.

## Phase 0: repository foundation

| ID | Issue | Status | Exit evidence |
|---|---|---|---|
| CT-000 | Establish repository, specification, workflow, and Phase 0 documentation | complete | Local validation passes and user reviews the uncommitted diff |
| CT-001 | Record environment and dependency-management decision | complete | ADR 0002 and reproducible setup commands |

## Phase 1: source profiling and ingestion

| ID | Issue | Status | Exit evidence |
|---|---|---|---|
| CT-101 | Investigate current CFPB API/export schema without downloading the full dataset | complete | `docs/cfpb_source_inventory.md` with versioned fields, risks, access finding, and bounded follow-up |
| CT-102 | Define bounded profiling query and fixture strategy | complete | Approved query boundary and non-sensitive test fixtures |
| CT-103 | Implement source metadata and bounded profiling command | complete | Deterministic report and mocked network tests |
| CT-104 | Decide local raw-data manifest and checksum format | complete | Approved manifest contract |
| CT-105 | Introduce PostgreSQL through a documented ADR | complete | Local database starts and readiness check passes |
| CT-106 | Implement append-only raw ingestion with batch metadata | complete | Disposable PostgreSQL test proves rollback, idempotency, row-count reconciliation, and mutation rejection |
| CT-107 | Implement staging transformations and quarantine reasons | complete | Versioned outcome contract and PostgreSQL acceptance/quarantine reconciliation tests |
| CT-108 | Implement retention-controlled real extraction and cleanup | pending | Approved-policy enforcement, bounded real batch, and deletion rehearsal |

## Phase 2: analytical dataset and baseline

| ID | Issue | Status | Exit evidence |
|---|---|---|---|
| CT-201 | Profile taxonomy stability and propose modelling window | complete | Accepted ADR 0007: 11-label identity taxonomy and `2023-09-01 <= date_received < 2025-01-01` |
| CT-202 | Define analytical population and exclusions | complete | Accepted ADR 0008 and tested versioned metadata-only population report |
| CT-203 | Implement temporal split and duplicate isolation | pending | Split manifest and leakage tests |
| CT-204 | Implement majority baseline | pending | Reproducible baseline report |
| CT-205 | Implement TF-IDF logistic-regression baseline | pending | Tracked training and evaluation run |
| CT-206 | Produce per-class and temporal baseline error analysis | pending | Generated report with limitations |

## Phase 3 onward

Later phases remain defined in `SPEC.md`. Expand them into issue-level detail only after the Phase 2 baseline checkpoint. This avoids committing prematurely to transformer, serving, and deployment details before the data is understood.

## Current next issue

Phase 2 is authorized and **CT-202 is complete**. ADR 0008 accepts a versioned
English-language eligibility funnel over the accepted taxonomy/window. ADR 0009
authorizes local real-data retention through 2026-11-19, but the loader remains
synthetic-only until CT-108 implements policy enforcement, bounded extraction,
and cleanup evidence. CT-108 is the next bounded issue; do not begin CT-203 until
a real eligible population exists.
