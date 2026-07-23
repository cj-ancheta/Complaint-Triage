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
| CT-108 | Enforce approved retention on real batch manifests | complete | Approved version/expiry/window enforcement and 16-month export design |
| CT-109 | Implement monthly streamed export and cleanup rehearsal | complete | Accepted tested writer, 16-shard run contract, 1 GiB shard cap, and safe cleanup evidence |
| CT-110 | Acquire, ingest, stage, and profile first real run | complete | Accepted reconciled 16-shard real aggregate population report under ADR 0009 |

## Phase 2: analytical dataset and baseline

| ID | Issue | Status | Exit evidence |
|---|---|---|---|
| CT-201 | Profile taxonomy stability and propose modelling window | complete | Accepted ADR 0007: 11-label identity taxonomy and `2023-09-01 <= date_received < 2025-01-01` |
| CT-202 | Define analytical population and exclusions | complete | Accepted ADR 0008 and tested versioned metadata-only population report |
| CT-203 | Implement temporal split and duplicate isolation | complete | Accepted reconciled metadata-only split manifest and leakage tests |
| CT-204 | Implement majority baseline | complete | Accepted reproducible aggregate baseline report |
| CT-205 | Implement TF-IDF logistic-regression baseline | review | Tracked training and evaluation run |
| CT-206 | Produce per-class and temporal baseline error analysis | pending | Generated report with limitations |

## Phase 3 onward

Later phases remain defined in `SPEC.md`. Expand them into issue-level detail only after the Phase 2 baseline checkpoint. This avoids committing prematurely to transformer, serving, and deployment details before the data is understood.

## Current next issue

Phase 2 is authorized and **CT-202 is complete**. ADR 0008 accepts a versioned
English-language eligibility funnel over the accepted taxonomy/window. ADR 0009
authorizes local real-data retention through 2026-11-19. CT-108 is complete with
fail-closed policy enforcement and an approved monthly export design. CT-109 is
complete with an accepted network-disabled streamed writer, exact run contract,
1 GiB shard cap, and dry-run-by-default cleanup rehearsal. CT-110 is complete:
the accepted retained 16-shard run reconciles 979,995 inputs to 979,194 eligible
and 801 excluded records, with zero staging quarantines. CT-203 is complete: its
accepted retained real run exactly reproduces the approved 561,342-row
deduplicated split, has zero included fingerprint overlap, and publishes
metadata-only evidence. CT-204 is complete: its accepted training-only majority
reference is reproducible from the split manifest and its aggregate report
reconciles all eleven classes. CT-205's validation-only rule, implementation,
training-only smoke, and real aggregate selection evidence are ready for review.
The test partition remains untouched and CT-205 is not complete until accepted.
