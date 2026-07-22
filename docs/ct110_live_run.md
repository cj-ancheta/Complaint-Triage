# CT-110 live-run record

## Adapter checkpoint

The live adapter is being prepared as a separate clean checkpoint before any
row-level request. It uses only Python's standard HTTPS client and the already
accepted streamed writer; no new transport dependency is required.

Safety gates before the first export body:

- exact confirmation `cfpb-local-120d-v1`;
- clean Git working tree and full HEAD SHA;
- at least 20 GiB free on the repository drive;
- successful aggregate-only profile with zero complaint rows;
- exactly 16 accepted months with no taxonomy drift; and
- every fresh count between 1 and 99,999.

## Aggregate preflight observed before implementation

At `2026-07-22T12:54:40.335440+00:00`, the existing aggregate profiler requested
zero complaint rows. All accepted months were present, no legacy or unexpected
labels appeared, and the 16 monthly counts reconciled to 979,995. The minimum was
38,894 and the maximum was 81,325. These are preflight observations, not frozen
download results; the live command must repeat them immediately before export.

## Pending completion evidence

CT-110 is not complete until the adapter is committed, the real run is acquired,
all 16 manifests reconcile, migrations are current, every shard is ingested and
staged, the analytical population is reported, and aggregate results plus peak
loader memory are recorded without row values.

The first acquisition attempt failed safely on the first record because the
official export omits `_source.has_narrative`. The pinned API source confirms
that omission is deliberate for export formats. The attempt rolled back its raw
artifact and manifest. Staging 1.1.0 therefore preserves the unmodified raw
payload and derives the filter guarantee only from the validated export request.
