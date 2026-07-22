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
