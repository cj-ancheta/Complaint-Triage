# CT-110 live-run record

## Adapter checkpoint

The live adapter was prepared as a separate clean checkpoint before any
row-level request. It uses only Python's standard HTTPS client and the already
accepted streamed writer; no new transport dependency was required.

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

## Completion conditions

The implementation required a committed adapter, a reconciled 16-shard run,
current migrations, complete ingestion and staging, an analytical population
report, and aggregate results plus peak loader memory without row values. All
conditions are satisfied, and Charles accepted the evidence and commit-safe
manifests on 2026-07-22.

The first acquisition attempt failed safely on the first record because the
official export omits `_source.has_narrative`. The pinned API source confirms
that omission is deliberate for export formats. The attempt rolled back its raw
artifact and manifest. Staging 1.1.0 therefore preserves the unmodified raw
payload and derives the filter guarantee only from the validated export request.

The second attempt also failed safely on record zero: the stored export field
uses an ISO date-time representation rather than the normal API's date-only
representation. Raw ingestion and staging now preserve that source string while
normalizing its calendar component for manifest reconciliation and typed dates.
The failed attempt again retained no JSON artifact or manifest.

The third attempt passed both source-shape checks and completed several shards,
then received HTTP 429. The pinned server throttle is two anonymous exports per
minute. The attempt rolled back, and the live adapter now spaces export starts
by at least 35 seconds rather than relying on download duration as implicit
pacing.

## Successful retained run

The paced run succeeded on 2026-07-22 with ID
`cfpb-run-20260722T130728Z-2b7815d4c850` and clean acquisition lineage
`46b7402d1b4537842d2f96ae1adbd7740a4e6560`.

Acquisition evidence:

- 16 of 16 monthly shards published;
- 979,995 preflight and returned records;
- 1,680,504,862 retained raw bytes;
- 16 content-addressed artifacts found by cleanup dry run;
- no response body or source value logged; and
- expiry fixed at `2026-11-19T15:59:59Z`.

Raw ingestion and staging evidence:

- 979,995 raw records across 16 immutable batches;
- 979,995 staging 1.1.0 outcomes;
- 979,995 staging accepted and zero quarantined; and
- largest measured raw-loader Python allocation 518,820,531 bytes on the
  81,325-record December 2024 shard.

Analytical population 1.0.0 evidence:

- 979,194 eligible records;
- 801 excluded records, all with `language_not_english`;
- eligible rate 0.999183;
- narrative length among eligible records: minimum 10, maximum 32,962, mean
  983.736 characters; and
- all raw, staging, population, status, product, and exclusion checks reconcile.

Eligible target counts:

| Product | Count |
|---|---:|
| Checking or savings account | 38,170 |
| Credit card | 47,562 |
| Credit reporting or other personal consumer reports | 746,849 |
| Debt collection | 82,045 |
| Debt or credit management | 1,838 |
| Money transfer, virtual currency, or money service | 13,210 |
| Mortgage | 16,227 |
| Payday loan, title loan, personal loan, or advance loan | 6,635 |
| Prepaid card | 5,002 |
| Student loan | 11,879 |
| Vehicle loan or lease | 9,777 |

The canonical aggregate report is
`data/manifests/cfpb/reports/cfpb-run-20260722T130728Z-2b7815d4c850.json`.
It contains no row values or narratives. These results are issue evidence only;
they are not approved README, portfolio, resume, or model-performance claims.
