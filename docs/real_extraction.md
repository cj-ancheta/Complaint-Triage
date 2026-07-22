# Monthly real-extraction operator guide

## Safety state

CT-109 provides the acquisition boundary but deliberately provides no HTTP
client or live acquisition CLI. Calling its functions with synthetic byte
streams cannot contact CFPB. CT-110 may add the narrow live adapter only after
this implementation is accepted and committed with a clean working tree.

Real data is authorized only under ADR 0009. It must remain under
`data/raw/cfpb/` and in the loopback-only Compose PostgreSQL volume. Do not copy
response bodies into terminals, logs, prompts, screenshots, notebooks, Git, or
cloud storage.

## Contract

`approved_monthly_shards()` returns exactly 16 adjacent half-open months from
2023-09-01 through 2025-01-01. Because CFPB's API upper date bound is inclusive,
the exported API range uses the final day of each month.

Before any body is requested, the caller must supply all 16 fresh aggregate
counts to `validate_preflight_counts()`. Missing months, non-positive counts, or
a count at or above the official 100,000-record export limit fail closed.

For each response, `publish_export_shard()`:

1. requires an approved shard, clean 40-character commit SHA, policy expiry,
   HTTP 200, no redirect, and JSON media type;
2. writes chunks beneath `data/raw/cfpb/.tmp/<run-id>/`, hashes the exact bytes,
   and stops above 1 GiB;
3. iteratively validates the top-level array, required fields, unique complaint
   IDs, non-empty narratives, product, and the half-open date boundary;
4. reconciles the exported count to the preflight count;
5. atomically publishes the content-addressed artifact and metadata-only batch
   manifest; and
6. removes partial or newly published artifacts when validation fails.

`publish_run_manifest()` accepts only the exact ordered 16-shard set with unique
batch/artifact identities and matching preflight/returned counts. The run
manifest is safe to commit because it contains paths, hashes, dates, and
aggregate counts—not complaint values.

## Cleanup rehearsal and operation

The cleanup CLI is an inventory command by default:

```powershell
complaint-triage cleanup-real-data --run-manifest data/manifests/cfpb/runs/<run-id>.json
```

Review the JSON inventory. It does not delete anything and does not print raw
paths or narratives. Irreversible cleanup requires both flags and the exact run
ID from the validated manifest:

```powershell
complaint-triage cleanup-real-data `
  --run-manifest data/manifests/cfpb/runs/<run-id>.json `
  --execute `
  --confirmation <run-id>
```

Execution deletes only content-addressed artifacts registered by that run and
`.part` files in that run's exact temporary directory. It then runs
`docker compose down --volumes --remove-orphans`, verifies the exact
`complaint-triage-ml_postgres_data` volume is absent, verifies no project
containers remain, and writes metadata-only evidence under
`data/manifests/cfpb/deletions/`.

Deletion is intentionally irreversible. The batch and run manifests remain as
permitted evidence. A failed verification returns a controlled error and must be
investigated before claiming deletion is complete.

## Synthetic verification

Run:

```powershell
python -m pytest tests/test_real_extraction.py
```

The tests cover monthly boundary generation, preflight limits, chunked writes,
redirect/content-type/status rejection, interruption cleanup, byte caps,
malformed records, date/narrative/schema drift, exact 16-shard reconciliation,
dry-run inventory, explicit confirmation, isolated file deletion, Docker command
verification, and safe error output. They use only visibly synthetic rows and a
fake Docker runner.
