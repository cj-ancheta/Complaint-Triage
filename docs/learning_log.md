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
