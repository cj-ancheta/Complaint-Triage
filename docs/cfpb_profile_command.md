# CFPB Bounded Profiling Command

- Issue: CT-103
- Status: complete with documented endpoint-access limitation
- Implemented: 2026-07-21
- Network requests per invocation: one
- Maximum returned hits accepted: five
- Maximum response body accepted: 2,000,000 bytes
- Raw response persistence: disabled

## Outcome

The repository now has a deterministic, metadata-only command for checking the
CFPB complaint search response contract. It makes one request using the exact
CT-102 URL and emits a derived JSON report without complaint narratives,
companies, complaint IDs, product values, or other individual source values.

CT-103 does not ingest data, write a raw file, introduce a database, select a
taxonomy, or train a model.

## Run the command

From the repository virtual environment:

```powershell
.\.venv\Scripts\python.exe -m complaint_triage profile-cfpb
```

After installing the package, the equivalent console entry point is:

```powershell
.\.venv\Scripts\complaint-triage.exe profile-cfpb
```

The command has no URL, date, size, export, or retry options. This is deliberate:
CT-103 is a source-contract probe, not a general extraction tool.

## Request controls

Before opening a connection, the command verifies:

- HTTPS;
- the exact `www.consumerfinance.gov` host;
- the documented complaint search API v1 path;
- no credentials, fragment, or non-standard port;
- the fixed one-day date window;
- `has_narrative=true`;
- `no_aggs=true`;
- `no_highlight=true`;
- `size=5`;
- `sort=created_date_desc`; and
- absence of `format`.

Changing any of these values in code without updating the approved contract
causes `unsafe_request_boundary` or `unsafe_request_parameters` before network
access.

The transport uses:

- `Accept: application/json`;
- a project-specific user agent;
- a 10-second timeout;
- one request and no retry; and
- a redirect handler that rejects all redirects.

Rejecting redirects is stricter than merely checking the destination host and
prevents the fixed endpoint boundary from changing silently.

## Response controls

The command checks the response in this order:

1. HTTP status is 200.
2. Content type is JSON.
3. A 2,000,001-byte sentinel read rejects any body above the 2,000,000-byte
   accepted limit.
4. The body parses as JSON.
5. The root, `_meta`, `hits`, `hits.total`, and each `_source` have the expected
   container types.
6. At least one and at most five hits are returned.
7. Every hit contains all 17 expected source fields.
8. Every hit has `has_narrative=true` and a non-empty narrative string.

Additive source fields are reported by name and observed JSON type. Their values
are never emitted. Missing expected fields fail the contract check.

## Safe success report

A successful report contains only:

- a fixed endpoint identifier and fixed request boundaries;
- request timestamp, HTTP metadata, duration, and byte count;
- source freshness flags, timestamps, license, and total record count;
- matching and returned counts;
- expected, observed, missing, and unexpected field names;
- per-field JSON type sets and null counts;
- narrative presence and length range; and
- explicit privacy and contract-check booleans.

The report excludes `_meta.break_points` because pagination cursors may contain
individual sort identifiers.

The command computes narrative length in memory but does not copy narrative text
into the report. It similarly observes field types without returning the values.

## Controlled failure report

Failures return exit code 1 and a JSON object containing a stable error code and
safe structural details. The raw exception and response body are suppressed.

Current error codes include:

| Code | Meaning |
|---|---|
| `unsafe_request_boundary` | Scheme, host, path, credentials, port, or fragment changed |
| `unsafe_request_parameters` | The approved fixed query changed |
| `network_error` | Timeout or URL-layer connection failure |
| `http_error` | The endpoint returned a non-200 status |
| `unexpected_content_type` | A 200 response was not JSON |
| `response_byte_limit_exceeded` | The response exceeded the local byte cap |
| `invalid_json_response` | The bounded body was not valid JSON |
| `invalid_response_shape` | A required response container had the wrong type |
| `empty_profile_result` | No hit was available for a field-contract check |
| `response_hit_limit_exceeded` | More than five hits were returned |
| `source_schema_missing_fields` | At least one hit omitted an expected field |
| `source_contract_check_failed` | Narrative presence checks failed |

Even on failure, the report states that the response body, source values, and raw
response were not logged or persisted.

## Test design

All automated network tests use an injected fake opener. The suite does not call
the live CFPB endpoint.

The focused tests verify:

- the exact request boundary;
- rejection of HTTP, another host, export format, six hits, and a wider date
  window;
- one request with the expected timeout and `Accept` header;
- safe type/null profiling from the synthetic fixture;
- suppression of narrative, company, complaint ID, product, additive-field, and
  pagination-cursor values;
- missing-field and more-than-five-hit failures;
- no body read for a non-JSON response;
- bounded body reads;
- suppression of invalid JSON content;
- no read or output of an HTTP error body; and
- CLI success and controlled-error serialization.

## Live smoke result

The command was invoked once from the current execution environment at
`2026-07-21T04:46:17.249120+00:00`. It reached the 10-second timeout and returned:

```json
{
  "error": {
    "code": "network_error",
    "requested_at_utc": "2026-07-21T04:46:17.249120+00:00"
  },
  "privacy": {
    "response_body_logged": false,
    "response_persisted": false,
    "source_values_logged": false
  },
  "status": "error"
}
```

This is consistent with the earlier CDN/access failure. No attempt was made to
bypass it. A successful HTTP 200 contract report remains outstanding and should
be captured only from an environment accepted by the public endpoint.

## Design decisions

### Standard library only

CT-103 uses `urllib`, `json`, `argparse`, and other Python standard-library
modules. A third-party HTTP client is not required for one fixed GET request, so
no runtime dependency was added.

The network layer is injected behind a small protocol for tests. This preserves a
clear migration path if a later ingestion issue justifies a more capable client.

### Derived report, not sanitized rows

The output is not a redacted version of the response. It is a new aggregate
object constructed from counts, types, field names, and approved metadata. This
is safer because adding a new live field does not automatically copy its value
into output.

### Strict request, tolerant additive schema

The request contract is exact because query drift could create an unbounded
download. The response contract tolerates additive fields by reporting their
names and types, because an upstream additive change should be investigated
without unnecessarily making the profiler unusable. Missing expected fields
remain a failure.

## CT-103 review checklist

- [x] Fixed CT-102 request is validated before network access.
- [x] One-request, timeout, redirect, byte, and hit limits implemented.
- [x] Success output contains only approved derived metadata.
- [x] Failure output suppresses bodies and raw exception text.
- [x] Pagination break points and individual hit values are excluded.
- [x] Mocked network and privacy tests added.
- [x] No runtime dependency added.
- [x] Live failure path exercised safely.
- [ ] Successful deployed HTTP 200 contract observed.
- [x] User reviewed and approved the CT-103 diff before commit.

## Next bounded issue

After review, CT-104 should decide the local raw-data manifest and checksum
contract. It must not begin downloading or retaining raw complaints until that
storage and lineage decision is approved.
