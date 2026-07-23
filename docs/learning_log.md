# Learning Log

Use one entry per completed issue. AI assistants may prepare a draft, but Charles should revise the verification and understanding sections after reviewing the work.

## Entry template

### `<issue ID>`: `<issue title>`

**Date:** YYYY-MM-DD

**What the AI generated**

Describe the files and behavior created.

**How I verified it**

Record commands, manual checks, and evidence inspected.

**What can fail in production**

Identify failure modes, not only coding errors.

**What I can explain in an interview**

Explain the design in your own words.

**Questions still open**

List anything that needs research or a future decision.

---

## Draft CT-000: repository foundation

**Date:** 2026-07-21

**What the AI generated**

The repository foundation, specification placement, AI-agent rules, standard Python packaging, lint and test configuration, smoke test, CI workflow, documentation skeleton, architecture decisions, and initial backlog.

**How I verified it**

Draft for Charles to complete after inspecting the diff and running or reviewing the validation commands.

**What can fail in production**

There is no production system yet. Future risks include dependency drift, unsupported environment assumptions, data leakage into Git, and allowing later AI-generated changes to cross phase gates without review.

**What I can explain in an interview**

Draft for Charles: why the backend and Lovable frontend are separate, why no data or modelling was added in Phase 0, and how the issue-level workflow protects learning and evidence quality.

**Questions still open**

See `docs/phase_0_review.md`.

---

## Draft CT-101: CFPB source inventory

**Date:** 2026-07-21

**What the AI generated**

A versioned inventory of official CFPB API fields, endpoints, bounded-search parameters, publication limitations, recent schema changes, leakage risks, privacy risks, and a proposed CT-102 live-contract check. It also recorded that the current execution environment received a CDN 403 without retrieving complaint data.

**How I verified it**

Draft for Charles to complete after reviewing `docs/cfpb_source_inventory.md` and following its links to the CFPB database, OpenAPI definition, field reference, release notes, and data-sharing page.

**What can fail in production**

The deployed API can diverge from the OpenAPI file, official pages can lag behind release changes, historical taxonomies can shift, recent narratives can be incomplete, and the endpoint can be blocked or unavailable from a deployment network.

**What I can explain in an interview**

Draft for Charles: why `product` is only a candidate target, why issue/sub-issue and response fields would leak information, why the database is not representative, and why a bounded request must omit the `format` parameter.

**Questions still open**

- Which `has_narrative` representation is accepted by the deployed API?
- Does the deployed field set exactly match the current OpenAPI contract?
- Which fixed historical date gives a small but non-empty bounded sample?
- What sanitized fixture strategy best supports deterministic tests?

---

## Draft CT-102: bounded profile contract and fixtures

**Date:** 2026-07-21

**What the AI generated**

A fixed-date, five-record CFPB request contract; client-side safety invariants;
allowed and forbidden profiling output; a hand-authored synthetic response
fixture; and automated tests that enforce its field shape and visible synthetic
markers. The exact request was attempted once and received CDN HTTP 403 without
logging or saving the response body.

**How I verified it**

Draft for Charles to complete after reviewing
`docs/cfpb_bounded_profile_plan.md`, inspecting the three synthetic records, and
running the repository validation commands. The deployed HTTP 200 response shape
still needs verification from a network environment accepted by the CFPB CDN.

**What can fail in production**

The deployed API can disagree with both its OpenAPI contract and source code,
optional fields can be null, complaint IDs can change type, additive fields can
appear, the endpoint can throttle or block a deployment network, and an unsafe
logger can expose narrative or company values even when the extraction itself is
bounded.

**What I can explain in an interview**

Draft for Charles: why `format` is deliberately absent, why the project applies a
client-side five-record limit despite permissive server code, why tests use
clearly synthetic narratives, and why a 403 is recorded as evidence rather than
bypassed.

**Questions still open**

- Does the deployed API return all 17 expected fields for the pinned query?
- Does the deployed API represent `complaint_id` as a string or integer today?
- Which additive OpenSearch hit metadata is present in the live response?

---

## Draft CT-103: bounded source profiling command

**Date:** 2026-07-21

**What the AI generated**

A standard-library command that makes one exact, five-hit CFPB contract request,
rejects URL or query drift, caps the body size, validates the response envelope,
and emits only derived metadata. It also generated fake-transport tests for
network, schema, limit, and privacy failure paths plus CLI serialization tests.

**How I verified it**

Draft for Charles to complete after inspecting `src/complaint_triage/cfpb_profile.py`,
reviewing `docs/cfpb_profile_command.md`, and running the focused and full test
suites. The live smoke test returned a controlled `network_error` after the
10-second timeout and did not print or save a response body.

**What can fail in production**

The endpoint can remain blocked, redirect, throttle, time out, return non-JSON,
exceed the byte or hit limit, change its response envelope, omit expected fields,
or change field types. A future developer could also weaken privacy by logging
the raw exception or response, so the privacy regression tests must remain.

**What I can explain in an interview**

Draft for Charles: why the command has no configurable extraction arguments, why
request strictness differs from additive-schema tolerance, why response-derived
aggregates are safer than redacted rows, why pagination cursors are excluded, and
how dependency injection keeps network tests deterministic.

**Questions still open**

- Can the command obtain HTTP 200 from the user's browser or another accepted
  network without changing its request boundary?
- What exact live types are returned for `complaint_id`, dates, tags, and nullable
  fields?
- Which batch-manifest and checksum contract should CT-104 use before any raw
  response is retained?

---

## Draft CT-104: raw batch manifest and checksum contract

**Date:** 2026-07-21

**What the AI generated**

A proposed content-addressed raw-storage ADR, a Draft 2020-12 manifest schema, a
comprehensive field and checksum contract, a synthetic manifest linked to the
existing synthetic response bytes, and tests for schema validity, exact-byte
SHA-256, canonical request fingerprints, aggregate reconciliation, safe relative
paths, and exclusion of individual source values.

**How I verified it**

Draft for Charles to complete after reviewing
`docs/cfpb_raw_batch_manifest.md`, comparing the synthetic manifest with its
schema, and running `tests/test_batch_manifest_contract.py` plus the full suite.
No live endpoint request or raw CFPB download was made in CT-104.

**What can fail in production**

An interrupted write can leave temporary bytes, a developer can hash reserialized
instead of stored JSON, line-ending or compression changes can alter exact-byte
digests, manifests can drift from their artifacts, unsafe row values can leak
into tracked metadata, concurrent acquisitions can race, and retention cleanup
can fail or delete the wrong path if CT-106 does not validate targets carefully.

**What I can explain in an interview**

Draft for Charles: why one batch, request, and artifact need different identities;
why exact-byte hashing differs from logical-JSON hashing; how content addressing
deduplicates bytes; why manifests are tracked while raw narratives are ignored;
and why atomic append-only writes improve recoverability.

**Questions still open**

- What retention policy ID and deletion behavior should apply to real raw CFPB
  artifacts?
- Will a future paginated acquisition need a separate run-level manifest?
- Should raw artifacts remain local-only or move to encrypted object storage for
  a later deployment?

---

## Draft CT-105: local PostgreSQL service

**Date:** 2026-07-22

**What the AI generated**

A proposed PostgreSQL ADR, pinned Docker Compose service, loopback-only port,
named volume, required environment credentials, container health check, Compose
contract tests, setup and lifecycle guide, and updated architecture status. It
also started the real service and ran readiness, version, encoding, and empty
user-table checks.

**How I verified it**

Draft for Charles to complete after reviewing `compose.yaml` and
`docs/postgresql_local.md`, running `docker compose config --quiet`, starting the
service with `--wait`, checking `docker compose ps`, and repeating the documented
`pg_isready` and SQL probes.

**What can fail in production**

Docker Desktop can be stopped, the host port can collide, an image pull can fail,
the named volume can be deleted, an exact tag can become outdated, initialization
variables do not update existing roles, a local superuser is inappropriate for
deployment, and a healthy server can still lack required migrations.

**What I can explain in an interview**

Draft for Charles: why the database is containerized, why the image tag and host
binding are explicit, how health differs from application readiness, how the
named volume preserves state, why `.env` is ignored, and why production would use
least-privilege roles rather than the local initialization superuser.

**Questions still open**

- Which SQLAlchemy, Alembic, and Psycopg versions should CT-106 select?
- What raw-artifact retention policy must be approved before real ingestion?
- Which schemas, role grants, and migration boundaries should the first database
  migration establish?

---

## Draft CT-106: append-only raw ingestion

**Date:** 2026-07-22

**What the AI generated**

A proposed raw-ingestion ADR; shared, redacted database settings; an Alembic
migration for batch and complaint JSONB tables; database mutation-rejection
triggers; a schema-, checksum-, lineage-, and reconciliation-validating loader;
safe CLI output; unit tests; a real disposable-PostgreSQL integration test; and a
CI PostgreSQL service. It selected current compatible Alembic, SQLAlchemy, and
Psycopg release lines and moved `jsonschema` into runtime dependencies because
every batch now depends on manifest validation.

**How I verified it**

Draft for Charles to complete after reviewing
`docs/decisions/0005-append-only-raw-ingestion.md`, following the synthetic
rehearsal in `docs/raw_ingestion.md`, inspecting the database counts, and running
the documented validation commands. The automated integration test created and
dropped a uniquely named database, forced a failure on the second record to prove
rollback, loaded three synthetic records, replayed the batch with zero new rows,
and confirmed that updates and deletes raise an append-only exception.

**What can fail in production**

A migration can be applied to the wrong database, database-owner credentials can
alter the append-only controls, concurrent writers can reveal an untested identity
edge case, local storage can fill, an evolving source envelope can fail strict
reconciliation, operational backups can outlive a future deletion, and future
code could misclassify real bytes as synthetic if marker checks are weakened. The
local initialization role is not suitable as a production application role.

**What I can explain in an interview**

Draft for Charles: why validation occurs before connecting; how exact-byte,
request, batch, and per-record hashes serve different purposes; why one database
transaction gives all-or-nothing ingestion; how conflict handling makes replay
idempotent; why JSONB belongs in the raw layer; why triggers complement rather
than replace application logic; and why real data remains blocked even though
the technical loader works.

**Questions still open**

- What retention duration, deletion evidence, and backup behavior should govern
  real CFPB artifacts and database rows?
- Should deployment split migration-owner and append-only writer roles?
- Should CT-107 quarantine schema-drifted rows or fail the complete staged batch?

---

## Draft CT-107: versioned staging outcomes

**Date:** 2026-07-22

**What the AI generated**

A proposed staging ADR, second Alembic migration, typed and deterministic
normalization module, closed quarantine-reason enum, aggregate-only CLI command,
shared disposable-database test fixture, unit tests, real PostgreSQL acceptance
and quarantine tests, and an operator/learning guide. No dependency was added.

**How I verified it**

Draft for Charles to complete after reviewing
`docs/decisions/0006-versioned-staging-outcomes.md`, comparing the reason table to
`src/complaint_triage/staging.py`, following the synthetic command in
`docs/staging_transformations.md`, and running the documented checks. The
PostgreSQL tests force rollback, accept three clean fixture rows, replay with zero
inserts, store malformed and duplicate rows with explicit reasons, reconcile all
counts, and reject updates and deletes.

**What can fail in production**

A source type can drift beyond the reason vocabulary, a transformation version
can be changed without a migration or documentation update, local storage can
grow because normalized narratives are duplicated, a database owner can disable
append-only triggers, canonical JSON behavior can be changed inconsistently,
and consumers can mistakenly treat staging acceptance as modelling eligibility.
Cross-batch and near-duplicate leakage remain unresolved by design.

**What I can explain in an interview**

Draft for Charles: why every raw row receives one outcome; why quarantine is a
data-quality result rather than an exception; how database checks encode count
reconciliation; why transformations are versioned and append-only; why Unicode,
line endings, nulls, dates, and hashes are normalized; why all within-batch
duplicates are quarantined; and why `product_raw` is not yet a canonical target.

**Questions still open**

- Which taxonomy versions and modelling window are stable enough to propose in
  Phase 2?
- How should cross-batch exact duplicates be assigned without temporal leakage?
- Which staging quarantine reasons, if any, should support a remediation flow?

---

## Draft CT-201: taxonomy stability and modelling-window proposal

**Date:** 2026-07-22

**What the AI generated**

A fixed aggregate-only CFPB taxonomy profiler, strict network/privacy boundary,
synthetic trends fixture, CLI command, unit tests, live aggregate evidence,
research note, and ADR. No dependency was added. Charles approved the eleven
current product labels with identity mapping and the September 2023 through
December 2024 modelling window on 2026-07-22.

**How I verified it**

Draft for Charles: review `docs/cfpb_taxonomy_stability.md`, compare its source
links and exact label strings to the official August 2023 form, run
`complaint-triage profile-taxonomy`, and confirm that all checks are true. The
observed live run returned 979,996 aggregate narrative-bearing records in the
candidate window, all 16 months, all 11 current labels, and no legacy or
unexpected label. Automated tests never call the network or contain complaint
rows.

**What can fail in production**

The upstream API can change parameters or response shape, historical aggregates
can be revised, a taxonomy can change again, the smallest classes can lose too
many rows during analytical filtering, the 2025 distribution shift can reduce
future performance, and an operator can misinterpret complaint counts as a
representative measure of consumer harm. The API's broad `dateRangeBuckets`
context must not be mistaken for the filtered product total.

**What I can explain in an interview**

Draft for Charles: why August 2023 is a mixed taxonomy month; why the first full
month begins the candidate window; why a clean pre-2025 baseline is preferable
to blindly maximizing recency; how an aggregate endpoint reduces privacy risk;
why exact identity labels are more defensible than an invented `Other` mapping;
and why 76% majority-class prevalence makes macro and per-class metrics essential.

**Questions still open**

- Which analytical exclusions will CT-202 propose, and how much class attrition
  will they cause?

---

## Draft CT-202: versioned analytical population

**Date:** 2026-07-22

**What the AI generated**

A shared accepted-taxonomy module; accepted population ADR; offline language
detector dependency; pure eligibility rules; append-only analytical migration;
streaming, idempotent database report; aggregate-only CLI output; operator guide;
and unit plus real PostgreSQL tests. No temporal split, cross-batch duplicate
rule, real-data result, or model was created.

**How I verified it**

Draft for Charles: review `docs/decisions/0008-proposed-analytical-population.md`,
trace each rule through `src/complaint_triage/analytical_population.py`, run the
documented command on an approved staged batch, and run the validation suite with
`RUN_POSTGRES_TESTS=1`. The integration test forces rollback, then reconciles one
eligible and four differently excluded synthetic rows, verifies replay, rejects
an unknown reason, and rejects table mutation.

**What can fail in production**

Language identification can misclassify short or mixed text, the 170 MB compiled
detector wheel may be unavailable on an unsupported platform, a large extract can
take substantial CPU time, real filtering can leave rare classes with inadequate
support, an upstream change can violate the staging contract, and multiple
reason counts can be mistaken for mutually exclusive row counts.

**What I can explain in an interview**

Draft for Charles: the difference between staging quality and modelling
eligibility; why every input receives a versioned outcome; why date/product checks
precede language detection; why undetermined language fails closed; why narrative
length is measured instead of filtered arbitrarily; how deferred foreign keys
allow atomic streaming inserts; and why duplicate isolation belongs with the
temporal split rather than this population filter.

**Questions still open**

- How should CT-108 encode the approved deadline and rehearse irreversible
  cleanup before acquiring the first real bounded batch?
- What temporal and duplicate-isolation options should CT-203 compare after the
  population decision is accepted?

---

## Draft CT-108: enforce real-manifest retention boundary

**Date:** 2026-07-22

**What the AI generated**

Manifest version 2 recognition for approved real batches, exact policy and expiry
validation, current-time expiry enforcement, clean-commit and accepted-window
checks, closed-schema support for an expiry timestamp, fail-closed tests, and an
official-source-grounded monthly extraction design. No real complaint was
downloaded or loaded.

**How I verified it**

Draft for Charles: review `docs/real_extraction_plan.md`, inspect the retention
branch in `prepare_raw_batch`, and run the raw-ingestion and manifest-contract
tests. The test data remains visibly synthetic even when it exercises the real
policy branch.

**What can fail in production**

The clock can be wrong, a streamed export can change shape or stop midway,
monthly counts can cross the official limit, source data can change between
preflight and export, local cloud-sync software can violate the storage boundary,
and a manifest policy check alone cannot delete expired Docker data.

**What I can explain in an interview**

Draft for Charles: why approval and enforcement are separate; why expiry is
checked against retrieval, current time, and an absolute deadline; why extraction
requires a clean commit; why monthly shards minimize data and stay below the
official cap; and why a streamed JSON array needs a new contract rather than a
shortcut through the old response parser.

**Questions still open**

- What byte cap and interruption-cleanup evidence should the synthetic writer
  tests establish before the first live request?

---

## CT-109: streamed monthly export and cleanup rehearsal

**Date:** 2026-07-22

Charles accepted the 1 GiB per-shard safety ceiling and the isolated synthetic
cleanup rehearsal on 2026-07-22.

**What the AI generated**

A fixed 16-month partition; inclusive-API-date mapping; all-month preflight
validation; a 1 GiB streamed hashing boundary; iterative JSON-array inspection;
atomic content-addressed artifact and safe-manifest publication; an exact run
contract; export-array ingestion support; and a dry-run-by-default cleanup CLI
with explicit confirmation, Compose-volume removal, verification, and safe
deletion evidence. No live HTTP adapter or real download was added.

**How I verified it**

Draft for Charles: review `docs/real_extraction.md`, inspect
`src/complaint_triage/real_extraction.py`, and run
`python -m pytest tests/test_real_extraction.py`. The tests use chunked synthetic
arrays and an isolated temporary repository. Docker calls are replaced with a
fake command boundary, so the rehearsal cannot remove the development database.

**What can fail in production**

Counts can change between preflight and export; a shard can reach the CFPB limit
or local byte cap; the upstream hit/source shape can change; disk space can run
out before atomic publication; machine clock or Git lineage can be wrong; Docker
may fail to remove a volume or container; and an external backup/sync tool can
violate ADR 0009 outside application control. The current raw loader still
materializes a prepared shard for transactional insertion, so CT-110 must measure
memory before loading all 16 batches.

**What I can explain in an interview**

Draft for Charles: why half-open analytical months map to inclusive API end
dates; why preflight and response counts must reconcile; why hashing while
writing does not replace structural validation; how a temporary file plus atomic
rename prevents partial publication; why content-addressing makes replay safe;
why deletion requires positive target identity and post-action verification; and
why HTTP transport remains gated until the boundary is reviewed from a clean
commit.

**Questions still open**

- How much memory does the current raw loader use for the largest real shard,
  and must CT-110 stream database insertion before processing the full run?

---

## CT-110: first retained real run

**Date:** 2026-07-22

**What the AI generated**

A clean-commit-gated HTTPS adapter, 20 GiB disk gate, fixed request validation,
35-second anonymous-export pacing, incomplete-run rollback, official export
compatibility for the omitted narrative flag and timestamp dates, staging 1.1.0,
and a reproducible aggregate-only run report. The approved 16-shard run was
acquired, ingested, staged, and filtered under ADR 0009.

**How I verified it**

Inspect `docs/ct110_live_run.md`; validate the run with the
cleanup command in dry-run mode; run `complaint-triage report-real-run` against
the recorded run manifest; and run the full test suite with PostgreSQL enabled.
The database-derived report checks all 16 identities and reconciles 979,995 raw,
staging, and population inputs without emitting row values.

**What can fail in production**

The upstream export schema can differ from the normal API schema, anonymous
requests can be throttled, counts can revise between runs, content-addressed raw
storage plus PostgreSQL can consume substantial disk, language detection is
CPU-heavy, the current loader peaks near 519 MB on the largest shard, and an
external sync or backup tool can violate the local-only retention policy.

**What I can explain in an interview**

Why a normal search contract cannot be assumed for bulk
exports; how clean lineage, aggregate preflight, pacing, streaming validation,
atomic publication, and rollback form separate controls; why raw source values
were preserved when staging normalized timestamps; how all 16 data layers were
reconciled; and why population prevalence is not a model-performance metric.

**Questions still open**

- What temporal split and duplicate-isolation policy should CT-203 adopt given
  the accepted population and severe class imbalance?

---

## CT-203: temporal split and duplicate isolation

**Date:** 2026-07-23

**What the AI generated**

An accepted split ADR, closed commit-safe manifest contract, append-only
PostgreSQL migration, streaming fingerprint pipeline, CLI command, operator
guide, synthetic leakage fixtures, and real aggregate split evidence. The
pipeline normalizes case and whitespace conservatively, excludes contradictory
label groups, retains one earliest same-label narrative, and assigns only the
canonical row by its own date.

**How I verified it**

Inspect `docs/temporal_split.md` and the generated split
manifest; rerun `complaint-triage build-temporal-split`; enable PostgreSQL tests
and run the full suite. The real database independently reconciles 979,194
outcomes, 561,342 unique included fingerprints, zero cross-split fingerprint
groups, valid date boundaries, and all eleven targets in every split.

**What can fail in production**

A partial population, unexpected date, invalid staging contract, dirty source
commit, database write rejection, manifest identity conflict, or changed rule
version fails closed. Exact normalized hashing does not catch paraphrases or
semantic near-duplicates, and aggressive fuzzy matching could incorrectly merge
different complaints. The deduplication rate also shows that naïve row counts
can substantially overstate independent training evidence.

**What I can explain in an interview**

Why future-facing evaluation uses whole-month temporal
boundaries; how grouping before assignment prevents leakage; why conflicting
labels invalidate an entire fingerprint group; why the canonical row is the
earliest observation; why the test set remains untouched during tuning; and why
the public manifest contains aggregate evidence while row-level fingerprints
remain in governed local storage.

**Questions still open**

- After CT-203 acceptance, should CT-204's majority baseline be defined globally
  from training labels only and evaluated unchanged on validation and test?
