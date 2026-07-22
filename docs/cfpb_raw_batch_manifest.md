# CFPB Raw Batch Manifest Contract

- Issue: CT-104
- Status: complete
- Contract version: 1.0.0
- Prepared: 2026-07-21
- Raw CFPB data downloaded: none

## Outcome

CT-104 defines how a future successful CFPB response will be identified,
checksummed, stored outside Git, and linked to a commit-safe lineage manifest.

The executable contract consists of:

- `contracts/cfpb-raw-batch-manifest.schema.json`;
- `tests/fixtures/cfpb/raw_batch_manifest_synthetic.json`; and
- `tests/test_batch_manifest_contract.py`.

This issue does not implement the writer, make a new source request, retain raw
CFPB data, start PostgreSQL, or ingest a database row.

## Three identities

| Identity | Answers | Construction |
|---|---|---|
| `batch_id` | Which acquisition event produced this manifest? | Retrieval UTC plus first 12 artifact-hash characters |
| `request_fingerprint_sha256` | Which exact safe request contract was used? | SHA-256 of canonical request JSON |
| `artifact.sha256` | Are these the exact stored response bytes? | SHA-256 of the byte-for-byte local artifact |

These values must not be substituted for one another. The same request can
produce new content later, and the same content can be observed by separate
acquisition events.

## Batch boundary

Manifest version 1 defines one successful HTTP response as one raw batch.

This intentionally avoids partial multi-page state. If a future ingestion run
uses several pages, each response receives its own content-addressed artifact and
batch manifest. A separate run-level manifest can later group those batches
without changing their identities.

The v1 commit-safe request object does not permit `search_term`, `format`,
`search_after`, complaint IDs, or arbitrary query keys. Pagination design is
therefore outside CT-104. Requested `size` is limited to 1 through 100 even if a
deployed server accepts a larger value.

## Local paths

### Raw artifact

```text
data/raw/cfpb/sha256/<first-two-hash-characters>/<full-sha256>.json
```

Example using the synthetic fixture:

```text
data/raw/cfpb/sha256/53/53db3b7b07c83080244508e02e45cd193c4a92327d5cb127add22fab75aa5426.json
```

Rules:

- paths recorded in manifests are repository-relative POSIX paths;
- absolute paths, drive letters, home directories, and `..` are forbidden;
- raw artifacts remain covered by `data/raw/` in `.gitignore`;
- a digest path is immutable;
- if the exact digest already exists, verify it and reuse it rather than rewrite
  it; and
- a file at the expected path with a different digest is corruption and must
  stop ingestion.

### Manifest

```text
data/manifests/cfpb/<batch-id>.json
```

The directory is intentionally not Git-ignored. A manifest is eligible for Git
only after schema validation and the row-value privacy tests pass.

## Artifact checksum

### Algorithm and representation

- algorithm: SHA-256;
- text representation: exactly 64 lowercase hexadecimal characters;
- scope: exact stored bytes;
- media type: `application/json`;
- content encoding for v1: `identity`; and
- file extension: `.json`.

Do not parse and reserialize the response before hashing. Whitespace, property
order, Unicode encoding, and final newline are part of the received byte stream
and therefore part of the digest.

The synthetic example is pinned to an LF checkout through `.gitattributes`, so
its exact-byte checksum is stable across Windows and Unix development machines.

### Future atomic-write sequence

CT-106 should implement this sequence without weakening it:

1. Accept only an approved HTTP 200 JSON response with identity encoding.
2. Stream to a uniquely named temporary file under `data/raw/cfpb/` while
   computing SHA-256 and byte count.
3. Flush and close the temporary file.
4. Validate the bounded JSON structure and aggregate counts without logging row
   values.
5. Derive the content-addressed destination from the completed digest.
6. If the destination exists, verify its digest; otherwise atomically move the
   temporary file into place.
7. Build and validate the manifest in memory.
8. Write the manifest through a separate temporary file and atomically publish
   it under `data/manifests/cfpb/`.
9. Never overwrite an existing artifact or manifest.

An interrupted response must not produce a completed batch manifest. Temporary
file cleanup behavior belongs to CT-106 and must use explicitly validated paths.

## Request fingerprint

The request fingerprint input is a JSON object containing:

```json
{
  "base_url": "<approved base URL>",
  "endpoint_id": "cfpb_complaint_search_v1",
  "method": "GET",
  "parameters": {},
  "schema": "complaint-triage-request-fingerprint-v1"
}
```

Canonicalize it using these exact rules:

- UTF-8;
- object keys sorted recursively;
- `ensure_ascii=false`;
- non-finite numbers rejected;
- separators `,` and `:` with no surrounding spaces; and
- no trailing newline.

Python reference operation:

```python
json.dumps(
    fingerprint_input,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
```

Hash those canonical bytes with SHA-256. The schema marker makes future
canonicalization changes explicit instead of silently changing fingerprints.

The fingerprint does not replace the structured request fields; both are stored
so a reviewer can understand and independently verify the hash.

## Batch identifier

Format:

```text
cfpb-YYYYMMDDTHHMMSSZ-aaaaaaaaaaaa
```

The timestamp comes from `response.retrieved_at_utc`, normalized to whole UTC
seconds. The suffix is the first 12 lowercase characters of `artifact.sha256`.

Example:

```text
cfpb-20260721T050000Z-53db3b7b07c8
```

The full artifact hash remains authoritative. The 12-character suffix is for
human recognition, not a standalone integrity guarantee.

## Manifest contents

### Identification

- manifest semantic version;
- batch ID;
- synthetic/real marker; and
- manifest creation timestamp.

### Source contract

- provider and dataset names;
- stable endpoint ID;
- official API-contract repository; and
- observed API-contract Git commit.

### Request

- method and base URL;
- explicit allowlisted parameters;
- fingerprint schema; and
- request fingerprint.

### Response metadata

- retrieval timestamp;
- HTTP status, media type, and content encoding;
- source freshness timestamps and flags;
- source license; and
- source total-record count.

Pagination break points are excluded because they can contain individual sort
identifiers.

### Artifact

- repository-relative content-addressed path;
- media type and encoding;
- byte count;
- hash algorithm and scope; and
- complete SHA-256 digest.

### Aggregate record observations

- returned and matching counts;
- unique and duplicate complaint-ID counts;
- non-empty narrative count; and
- observed receipt-date minimum and maximum.

No complaint ID or narrative value is stored.

### Schema observation

- sorted source-field names;
- field count; and
- observed JSON types for complaint IDs.

The complaint-ID type remains explicit because the current OpenAPI contract and
historical official fixtures disagree.

### Code lineage

- extractor name and semantic version;
- full 40-character repository commit;
- clean/dirty working-tree flag; and
- Python version.

A production acquisition should use committed code and record a clean working
tree. The schema records the boolean rather than fabricating cleanliness.

### Privacy controls

- acknowledgement that the ignored artifact contains public narratives;
- assertion that the raw artifact is not Git tracked;
- assertion that the manifest contains no row values;
- whether the validated manifest may be tracked; and
- retention-policy identifier.

## Commit-safety boundary

Allowed in a tracked manifest:

- URLs and allowlisted fixed query values;
- timestamps, counts, hashes, versions, flags, and license;
- field names and JSON type names; and
- repository-relative ignored paths.

Forbidden in a tracked manifest:

- narratives or fragments;
- complaint IDs;
- company, product, issue, state, ZIP, tag, or response values;
- raw pagination cursors;
- full response objects;
- local absolute paths; and
- credentials, headers, cookies, tokens, or proxy configuration.

The manifest is an aggregate lineage record, not a redacted response.

## Schema evolution

`manifest_version` follows semantic versioning:

- major: an incompatible field, meaning, canonicalization, checksum, or storage
  change;
- minor: a backwards-compatible optional field; and
- patch: clarification that does not change valid JSON instances.

Published batch manifests are immutable. If lineage is wrong, quarantine the
manifest and produce a replacement batch or explicit correction record; do not
edit history silently.

## Dependency decision

CT-104 adds `jsonschema` as a development-only dependency. Python's standard
library parses JSON but does not implement Draft 2020-12 validation. The package
is used in tests to validate the schema itself and the synthetic example. No
runtime ingestion dependency is added.

## Retention boundary

No production retention duration or deletion schedule is approved in CT-104.
The manifest has `retention_policy_id`, but CT-106 must not persist a real raw
artifact until a concrete policy identifier and local cleanup behavior are
reviewed. The synthetic example uses
`not-applicable-synthetic-fixture`.

## CT-104 acceptance checklist

- [x] Batch, request, and artifact identities separated.
- [x] Exact-byte SHA-256 algorithm and scope defined.
- [x] Content-addressed relative raw path defined.
- [x] Commit-safe manifest path and field boundary defined.
- [x] Single-response v1 batch boundary defined.
- [x] Canonical request fingerprint defined.
- [x] Append-only and atomic-write expectations documented.
- [x] Draft 2020-12 JSON Schema added.
- [x] Synthetic example validates against the schema.
- [x] Exact fixture checksum, byte count, counts, and privacy assertions tested.
- [x] No raw CFPB response downloaded or retained.
- [x] User approved the proposed contract and ADR on 2026-07-22.

## Accepted decisions

CT-104 approval accepts:

1. SHA-256 over exact identity-encoded stored bytes.
2. One HTTP response per v1 batch.
3. Content-addressed raw storage outside Git.
4. Separate commit-safe manifests under `data/manifests/cfpb/`.
5. Canonical request fingerprints using the v1 rules above.
6. No real raw acquisition until retention behavior is separately approved.

After approval, CT-105 may introduce PostgreSQL through its own ADR. CT-104 does
not authorize CT-106 ingestion.
