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
| CT-205 | Implement TF-IDF logistic-regression baseline | complete | Accepted tracked training and validation run |
| CT-206 | Produce per-class and temporal baseline error analysis | complete | Accepted generated report with limitations |

## Phase 3: deep-learning candidate

| ID | Issue | Status | Exit evidence |
|---|---|---|---|
| CT-301 | Select the compact encoder boundary and profile tokenizer truncation | complete | Accepted ADR 0012, 384-token boundary, and reproducible training-only aggregate report |
| CT-302 | Implement the versioned transformer dataset and tokenizer pipeline | complete | Accepted deterministic streaming loaders, length-grouped dynamic padding, and real aggregate validation |
| CT-303 | Train and track the compact transformer candidate | complete | Accepted epoch-3 validation selection, aggregate report, and hashed local safetensors artifact |
| CT-304 | Compare baseline and transformer on validation evidence | complete | Accepted aggregate validation comparison advances MiniLM to CT-305; test remains untouched and final selection remains deferred |
| CT-305 | Calibrate the selected candidate probabilities | complete | Accepted temperature-scaling report and governed calibrator advance calibrated MiniLM probabilities to CT-306; test remains untouched |
| CT-306 | Record the baseline-versus-transformer decision | complete | Accepted six-gate report selects calibrated MiniLM within the approved CPU, memory, artifact, explainability, complexity, and cost boundaries |

## Phase 4: abstention and final evaluation

| ID | Issue | Status | Exit evidence |
|---|---|---|---|
| CT-401 | Implement and run validation-only abstention threshold analysis | in progress | Reviewed command and schema, synthetic validation, then accepted aggregate October report with test untouched |
| CT-402 | Approve one proposed threshold and run the frozen final test once | pending | Separate threshold approval, one aggregate test report, and no threshold retuning |
| CT-403 | Assemble the model card and governance evidence pack | pending | Reviewed limitations, intended-use boundary, evidence lineage, and release decision |

Later serving and deployment phases remain defined in `SPEC.md` and will be
expanded only after the Phase 4 evidence gates are accepted.

## Current next issue

ADR 0016 and the Phase 3 to Phase 4 transition are accepted. CT-401 is the only
active issue. Its implementation is awaiting synthetic validation and review;
the real October run must start from the subsequently approved clean commit.
The frozen test partition remains untouched. CT-402, threshold approval,
deployment, and public metric promotion remain separate explicit gates.
