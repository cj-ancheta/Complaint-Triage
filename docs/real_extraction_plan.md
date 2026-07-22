# Retention-controlled real extraction plan

## CT-108 boundary

CT-108 prepares the repository to recognize real manifests governed by accepted
ADR 0009. It does not download a real complaint, weaken path/checksum controls,
or implement the different streamed-export envelope.

Charles approved this boundary and the 16-month extraction design on 2026-07-22.

The loader accepts a real manifest only when all of these are true:

- manifest version is `2.0.0`;
- retention policy is exactly `cfpb-local-120d-v1`;
- an explicit UTC expiry exists, is after retrieval and the current time, and is
  no later than `2026-11-19T15:59:59Z`;
- extraction lineage says the working tree was clean;
- the request is wholly inside
  `2023-09-01 <= date_received < 2025-01-01`;
- existing exact artifact path, checksum, byte-count, fingerprint, batch-ID,
  schema, and count reconciliation checks pass; and
- the manifest contains no row values under its closed schema.

Synthetic fixtures remain on manifest version `1.0.0`, cannot claim an expiry,
and retain their synthetic-marker checks.

## Official acquisition evidence

The [official CFPB database page](https://www.consumerfinance.gov/data-research/consumer-complaints/)
offers full CSV/JSON downloads and filtered export. The current official UI
source at commit `bd6f3d2d9972e9567a617fff39c74da322035d6c` limits a filtered export to
100,000 complaints. The current official API source at commit
`f10324b3e42c146fc6de1caacfb0bb63691e6b4a` confirms that JSON exports are
streamed arrays and reject totals above that limit.

This is a different envelope from manifest v1's normal search response. It must
receive a new writer/parser contract rather than being forced through the old
one-response assumptions.

## Approved extraction partition

Use one filtered JSON export for each calendar month in the accepted window:

```text
2023-09-01 <= date_received < 2023-10-01
...
2024-12-01 <= date_received < 2025-01-01
```

The aggregate profile observed 16 monthly counts between 38,894 and 81,325 on
2026-07-22, so every shard was below the official 100,000 limit. The observed
total was 979,995 in the later check, one below the earlier 979,996 observation;
this small upstream revision is why the extraction must record its own count and
timestamp rather than copy a research number into a manifest.

Monthly filtered exports are preferable to:

- the full download, which would temporarily retain millions of out-of-scope
  complaints; or
- 100-row pagination, which would require roughly 10,000 requests and create an
  unnecessarily complicated consistency window.

## Accepted CT-109 implementation

CT-109 implements the following controls without adding a live HTTP transport:

1. define a run manifest grouping all 16 monthly shards;
2. generate only fixed month boundaries and approved query parameters;
3. perform a fresh aggregate preflight and reject a shard at or above 100,000;
4. stream each response into a unique temporary file under the ignored raw-data
   boundary while hashing and enforcing a byte cap;
5. reject redirects, non-JSON content, partial responses, array/schema drift,
   unexpected dates, empty narratives, and counts that do not reconcile;
6. atomically publish content-addressed artifacts and commit-safe manifests;
7. prove interruption cleanup and replay with synthetic streamed fixtures;
8. implement a dry-run cleanup inventory and an isolated deletion rehearsal; and
9. require a clean committed CT-109 implementation before the live command can
   run.

The API's `date_received_max` becomes an inclusive OpenSearch `to` bound. The
code therefore represents each approved month as a half-open interval but sends
the last calendar day as the API maximum. This prevents adjacent shards from
overlapping.

The fixed per-shard ceiling is 1 GiB. Bytes are written and hashed incrementally;
`ijson` then validates each array item without materializing the full array. The
cap is a safety boundary, not an expected payload-size claim. CT-110 must stop
for review if a legitimate shard reaches it.

Charles accepted the 1 GiB shard ceiling and synthetic cleanup boundary on
2026-07-22. See `docs/real_extraction.md` for the operator and cleanup workflow.
No live request should occur until this implementation is committed and the
CT-110 adapter re-verifies a clean working tree.
