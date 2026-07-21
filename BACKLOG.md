# Initial Implementation Backlog

This backlog converts `SPEC.md` into bounded delivery issues. Status values are `pending`, `in progress`, `review`, `complete`, or `blocked`.

## Phase 0: repository foundation

| ID | Issue | Status | Exit evidence |
|---|---|---|---|
| CT-000 | Establish repository, specification, workflow, and Phase 0 documentation | review | Local validation passes and user reviews the uncommitted diff |
| CT-001 | Record environment and dependency-management decision | complete | ADR 0002 and reproducible setup commands |

## Phase 1: source profiling and ingestion

| ID | Issue | Status | Exit evidence |
|---|---|---|---|
| CT-101 | Investigate current CFPB API/export schema without downloading the full dataset | pending | Versioned field inventory and source-risk notes |
| CT-102 | Define bounded profiling query and fixture strategy | pending | Approved query boundary and non-sensitive test fixtures |
| CT-103 | Implement source metadata and bounded profiling command | pending | Deterministic report and mocked network tests |
| CT-104 | Decide local raw-data manifest and checksum format | pending | Approved manifest contract |
| CT-105 | Introduce PostgreSQL through a documented ADR | pending | Local database starts and readiness check passes |
| CT-106 | Implement append-only raw ingestion with batch metadata | pending | Idempotency and row-count tests |
| CT-107 | Implement staging transformations and quarantine reasons | pending | Data-contract and reconciliation tests |

## Phase 2: analytical dataset and baseline

| ID | Issue | Status | Exit evidence |
|---|---|---|---|
| CT-201 | Profile taxonomy stability and propose modelling window | pending | User-approved taxonomy and date window |
| CT-202 | Define analytical population and exclusions | pending | Versioned population report |
| CT-203 | Implement temporal split and duplicate isolation | pending | Split manifest and leakage tests |
| CT-204 | Implement majority baseline | pending | Reproducible baseline report |
| CT-205 | Implement TF-IDF logistic-regression baseline | pending | Tracked training and evaluation run |
| CT-206 | Produce per-class and temporal baseline error analysis | pending | Generated report with limitations |

## Phase 3 onward

Later phases remain defined in `SPEC.md`. Expand them into issue-level detail only after the Phase 2 baseline checkpoint. This avoids committing prematurely to transformer, serving, and deployment details before the data is understood.

## Current next issue

After CT-000 is reviewed and committed, proceed with **CT-101: investigate the current CFPB API/export schema without downloading the full dataset**.

CT-101 is research and profiling only. It must not implement database ingestion or modelling.

