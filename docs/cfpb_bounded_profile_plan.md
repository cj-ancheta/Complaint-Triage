# CFPB Bounded Profile Contract

- Issue: CT-102
- Status: review
- Prepared: 2026-07-21
- Scope: one bounded source-contract check and a synthetic fixture strategy
- Raw CFPB records retained: none

## Outcome

CT-102 fixes the request boundary, safe output policy, expected response shape, and
deterministic fixture contract needed before a profiling command is implemented.

The proposed request can return at most five ordinary search hits. It
does not request an export, aggregations, or highlights. A live attempt from this
execution environment received HTTP 403 from the CFPB CDN, so the deployed
response shape is not yet verified. That remaining check must be performed from
an environment that the public endpoint accepts before CT-102 is marked complete.

No database, ingestion pipeline, modelling code, or target-taxonomy decision is
part of this issue.

## Evidence used

This plan builds on `docs/cfpb_source_inventory.md` and the official CFPB API
repository at commit `b4f292524c40e4fd154b9350bf8335ade3e0b5e9`.

The official implementation adds several details that are not obvious from the
OpenAPI page:

- normal searches default to 25 hits in `complaint_search/defaults.py`;
- `SearchInputSerializer` accepts an integer `size` from 0 through 20,000,000,
  despite the narrower OpenAPI description;
- the source tests exercise `has_narrative=["true"]`;
- `has_narrative` is passed directly into an OpenSearch `terms` filter;
- `created_date_desc` is translated to descending `date_received` sorting;
- `no_aggs=true` omits the large aggregation section;
- `no_highlight=true` omits narrative highlight fragments; and
- anonymous non-export search is throttled at 20 requests per minute.

These inconsistencies are a reason to impose a client-side maximum. A server-side
maximum alone is not a safe extraction boundary.

## Pinned request contract

### Exact request

```text
GET https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/?date_received_min=2024-01-02&date_received_max=2024-01-03&has_narrative=true&no_aggs=true&no_highlight=true&size=5&sort=created_date_desc
Accept: application/json
```

The dates select one fixed historical day in the post-August-2023 publication
period. This is a source-contract probe only; it does not select the eventual
modelling population or taxonomy.

### Why each parameter exists

| Parameter | Pinned value | Reason |
|---|---|---|
| `date_received_min` | `2024-01-02` | Makes the request reproducible and avoids an unbounded recent search |
| `date_received_max` | `2024-01-03` | Defines the following-day upper boundary for a one-day window |
| `has_narrative` | `true` | Matches the current official source test and limits results to the candidate text population |
| `no_aggs` | `true` | Avoids unnecessary aggregation payload and compute |
| `no_highlight` | `true` | Avoids duplicate narrative fragments in the response |
| `size` | `5` | Establishes the client-approved maximum for contract profiling |
| `sort` | `created_date_desc` | Provides deterministic requested ordering; current source maps this to `date_received` descending |

### Parameters deliberately omitted

- `format`: supplying `json` or `csv` invokes export behavior and causes `size`
  and `frm` to be ignored.
- `frm`: not needed for the first page and subject to contract inconsistencies.
- `search_term`: not needed to inspect the source schema.
- `product` and `issue`: would pre-select taxonomy values before CT-201.
- `company`, geography, tags, and response fields: not needed for the contract
  check and inappropriate as MVP model features.

### Request invariants for CT-103

The future profiling command must enforce these locally before making a request:

1. The scheme is HTTPS and the host is exactly `www.consumerfinance.gov`.
2. The path is the documented complaint search API v1 path.
3. `size` is an integer from 1 through 5.
4. Both dates are present and the maximum is later than the minimum.
5. The interval is no greater than one day for the initial probe.
6. `format` is absent.
7. `no_aggs` and `no_highlight` are true.
8. The request timeout is finite.
9. Redirects to another host are rejected or require explicit review.
10. The command makes one request per invocation and does not retry a 4xx
    response automatically.

The API advertises a 20-per-minute anonymous search throttle. The project should
remain far below it: one manual contract probe is sufficient. A future retry for
transient 5xx or network failure must use a small bounded count and backoff, but
that behavior belongs to CT-103.

## Safe profiling output

The command may print or persist only a derived profile. It must never print the
raw response or any individual source value.

### Allowed output

- request timestamp in UTC;
- redacted request identity or parameter names;
- HTTP status and content type;
- elapsed time and response byte count;
- `_meta` freshness flags and source license;
- matching total and returned hit count;
- the union of observed `_source` field names;
- expected, missing, and unexpected field names;
- per-field observed JSON types and null counts;
- narrative-present count and narrative-length minimum/maximum, computed without
  retaining or displaying text; and
- boolean assertions such as `returned_hits_lte_5`.

### Forbidden output

- complaint narrative text or fragments;
- company, state, ZIP, tag, complaint ID, or other individual values;
- full URLs if they could later contain user-supplied query text;
- the raw JSON response;
- stack traces containing response bodies; and
- examples copied from live CFPB rows into tests, reports, or Git history.

The first implementation should build the derived profile in memory and discard
the response after validation. It must not create `data/raw` files.

## Expected response envelope

The current OpenAPI contract describes an object containing:

```text
_meta
  break_points
  has_data_issue
  is_data_stale
  is_narrative_stale
  last_indexed
  last_updated
  license
  total_record_count
hits
  total.value
  total.relation
  max_score
  hits[]
    _source
```

OpenSearch may also return hit metadata such as `_id`, `_index`, `_score`, and
`sort`. CT-103 should ignore those values except where needed for structural
validation. Additive top-level or hit-level keys should be reported, not treated
as an immediate failure. Missing required source fields should fail the contract
check.

### Expected `_source` fields

The current expected set contains 17 fields:

```text
company
company_public_response
company_response
complaint_id
complaint_what_happened
date_received
date_sent_to_company
has_narrative
issue
product
state
submitted_via
sub_issue
sub_product
tags
timely
zip_code
```

The contract must tolerate null optional values. It must also temporarily accept
`complaint_id` as either a JSON string or integer because the OpenAPI schema says
integer while the official API repository's historical response fixtures contain
strings. CT-103 must report the observed runtime type so a later ingestion
contract can normalize it deliberately.

## Synthetic fixture strategy

The fixture at `tests/fixtures/cfpb/search_response_synthetic.json` models only
the expected response structure. Every narrative begins with `SYNTHETIC TEST
RECORD`, every company name begins with `SYNTHETIC`, and identifiers use a `SYN-`
prefix.

The fixture intentionally covers:

- three hits, below the five-record boundary;
- all 17 expected source fields;
- nullable optional fields;
- string complaint IDs, reflecting the type discrepancy to be handled;
- a non-ASCII narrative character to exercise UTF-8 handling;
- an optional tag to ensure it can be identified and excluded later; and
- no aggregation object, matching `no_aggs=true`.

The product and issue values are synthetic placeholders. They are not CFPB
taxonomy claims and must not be used to choose classes. CT-201 remains responsible
for taxonomy analysis and approval.

### Fixture provenance policy

- Do not copy, paraphrase, or sanitize a real complaint into a committed fixture.
- Hand-author records that are plainly fictional and contain no names, addresses,
  account numbers, email addresses, phone numbers, or real company names.
- Keep the fixture small enough for human review.
- Validate the marker and field set in an automated test.
- If the live API adds fields, first document the change; do not silently copy a
  live row into the fixture.
- Real response bodies, if later retained for ingestion, belong under ignored raw
  data storage with a manifest and retention decision from CT-104 onward.

## Live-check procedure

Run the eventual CT-103 command from an environment that can reach the official
API. Until that command exists, a manual browser or shell check may be used only
if it follows the same output restrictions.

1. Confirm the exact URL and five-record maximum before sending.
2. Send one request with `Accept: application/json`.
3. If the result is not HTTP 200, record only status, content type, timestamp, and
   whether a body was suppressed; then stop.
4. If the result is HTTP 200, assert the content type is JSON before parsing.
5. Assert returned hit count is at most five.
6. Compute the allowed derived profile without printing source values.
7. Confirm every returned hit has `has_narrative=true` and non-empty narrative
   text without displaying the text.
8. Compare the observed field set and types with this contract.
9. Discard the response object.
10. Attach only the redacted derived profile to the review evidence.

If more than five hits are returned, if an export-shaped response is detected, or
if the schema is materially different, stop and investigate before writing data.

## Live-access result from this environment

The exact pinned request was attempted once on 2026-07-21 at
`04:32:41.5623134Z`.

```text
status=403
content_type=<not supplied>
body_logged=false
```

No response body, hit, company value, complaint ID, or narrative was printed or
saved. The CDN restriction was not bypassed.

## CT-102 review checklist

- [x] Exact fixed-date, five-record request defined.
- [x] Export behavior explicitly excluded.
- [x] Official implementation details and throttle reviewed.
- [x] Allowed and forbidden profiling output defined.
- [x] Expected response and 17-field source contract defined.
- [x] Synthetic, non-sensitive fixture added.
- [x] Automated fixture safety and shape tests added.
- [x] Exact bounded live attempt made without retaining a body.
- [ ] HTTP 200 response contract verified from an accepted network environment.
- [ ] User reviews and approves the boundary before CT-103 begins.

## Decision needed at review

Approve the pinned request and synthetic fixture approach. If approved, CT-103
can implement a small metadata-only profiling command with mocked network tests.
The first successful live run will close the remaining deployed-contract check.
