# ADR 0003: Content-Address Raw CFPB Batches

- Status: accepted
- Date: 2026-07-21
- Accepted: 2026-07-22
- Issue: CT-104

## Context

Future CFPB ingestion must prove which response bytes produced a database batch
without committing public complaint narratives to Git. The upstream dataset is
mutable, identical queries can produce different responses over time, and JSON
can be reserialized into different bytes without changing its logical content.

A single identifier cannot reliably represent the acquisition event, request,
and stored artifact. Absolute local paths would also make manifests machine
specific, while recording response rows or pagination cursors could place
individual complaint values in Git.

## Decision

Use three separate identities:

1. `batch_id` identifies one successful HTTP acquisition event.
2. `request_fingerprint_sha256` identifies the canonical request contract.
3. `artifact.sha256` identifies the exact response bytes stored locally.

For manifest version 1, one successful HTTP response is one batch. Store its raw,
identity-encoded JSON bytes without reformatting at:

```text
data/raw/cfpb/sha256/<first-two-hash-characters>/<full-sha256>.json
```

Raw artifacts remain Git-ignored. Store the corresponding row-free manifest at:

```text
data/manifests/cfpb/<batch-id>.json
```

The manifest may be committed only after contract and privacy validation. Use the
Draft 2020-12 schema in
`contracts/cfpb-raw-batch-manifest.schema.json` as the authority.

SHA-256 is lowercase hexadecimal. The artifact digest covers the exact stored
bytes, not parsed or reserialized JSON. The request digest covers canonical
UTF-8 JSON with sorted keys and compact separators as specified in the CT-104
contract.

The batch identifier is:

```text
cfpb-<retrieval UTC as YYYYMMDDTHHMMSSZ>-<first 12 artifact hash characters>
```

Artifacts and manifests are append-only. Existing bytes or manifests must never
be silently overwritten. Identical artifact content may be referenced by more
than one acquisition manifest without storing duplicate raw bytes.

Manifest version 1 permits only identity content encoding and a safe, explicit
query field set. It does not support raw pagination cursors or search terms in a
commit-safe manifest.

## Consequences

Benefits:

- exact corruption checks and reproducible lineage;
- content-based deduplication of identical raw responses;
- query changes are distinguishable from source-content changes;
- manifests can be reviewed in Git without exposing complaint rows;
- relative POSIX paths work across development machines; and
- upstream schema observations remain linked to exact bytes.

Costs:

- one acquisition produces both an ignored artifact and a separate manifest;
- exact-byte hashes change if content is reformatted or compressed;
- multi-page runs require multiple v1 batch manifests;
- a future run-level manifest may be needed to group pages; and
- production retention cannot begin until a separate retention policy is
  approved.

## Alternatives considered

### Hash parsed, canonicalized JSON

Rejected for the raw artifact. Canonicalization could hide byte-level changes and
would mean the checksum no longer proves the stored file is identical to the
received payload.

### Timestamp-only filenames

Rejected because they do not detect duplicate content or corruption and can
collide under concurrent work.

### Store raw files beside tracked source code

Rejected because complaint narratives and row-level metadata must stay out of
Git.

### One manifest containing several response pages

Deferred. A single-response v1 contract gives simpler atomic writes and failure
recovery. Introduce a higher-level run manifest only when a bounded pagination
design is approved.

## Revisit triggers

Create a new ADR and manifest major version before:

- storing compressed or encrypted raw artifacts;
- changing the hash algorithm or hash scope;
- introducing object storage or remote artifact URIs;
- recording pagination cursors in tracked metadata;
- combining several responses into one batch; or
- treating manifests as a database registry rather than Git-reviewed lineage.
