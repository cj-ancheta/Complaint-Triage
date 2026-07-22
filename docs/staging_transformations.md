# Versioned staging transformations

CT-107 converts an immutable raw batch into typed, versioned source-quality
outcomes. It creates no training dataset and selects no canonical product
taxonomy.

## Data flow

```text
raw.ingestion_batches + raw.complaints
                    |
                    v  transformation 1.1.0
staging.transformation_batches
staging.complaint_outcomes
      | accepted       | quarantined + reason codes
      +----------------+----------------------------> later analytical decision
```

Every raw row produces exactly one staging outcome for version 1.1.0. Database
constraints require input and output counts to match and require accepted plus
quarantined counts to equal the output count.

## Apply the migration

```powershell
docker compose up -d --wait postgres
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

The current head is `0002_staging_outcomes`. Downgrading to
`0001_raw_ingestion` drops the complete staging schema and all its outcomes; use
that only with a disposable database.

## Stage an ingested batch

First complete the synthetic rehearsal in `docs/raw_ingestion.md`. Then use the
batch ID printed by ingestion:

```powershell
.\.venv\Scripts\python.exe -m complaint_triage stage-raw-batch `
  --batch-id cfpb-20260721T050000Z-53db3b7b07c8
```

The first valid run returns aggregate-only JSON like:

```json
{
  "accepted_record_count": 3,
  "input_record_count": 3,
  "inserted_record_count": 3,
  "privacy": {
    "raw_payload_logged": false,
    "source_values_logged": false
  },
  "quarantined_record_count": 0,
  "raw_batch_id": "cfpb-20260721T050000Z-53db3b7b07c8",
  "status": "staged",
  "transformation_version": "1.1.0"
}
```

Running it again returns `already_staged` and zero inserted records after
rechecking stored outcome counts.

## Inspect counts safely

Prefer aggregate queries during routine verification:

```powershell
docker compose exec postgres psql `
  -U complaint_triage -d complaint_triage `
  -c "SELECT raw_batch_id, transformation_version, input_record_count, accepted_record_count, quarantined_record_count, output_record_count FROM staging.transformation_batches;"

docker compose exec postgres psql `
  -U complaint_triage -d complaint_triage `
  -c "SELECT outcome_status, quarantine_reasons, count(*) FROM staging.complaint_outcomes GROUP BY outcome_status, quarantine_reasons ORDER BY outcome_status;"
```

Do not select narratives into terminals, CI logs, screenshots, or tickets. The
database contains normalized narratives because later transformations need them;
normal CLI output does not reproduce them.

## Quarantine behavior

The authoritative reason vocabulary is the `QuarantineReason` enum in
`src/complaint_triage/staging.py` and is explained in ADR 0006. Multiple reasons
can apply to one row. Their order is deterministic.

Within-batch duplicate IDs are all quarantined. The command does not select a
preferred duplicate. It also does not claim to resolve duplicates across batches
or near-duplicate narratives; those require approved analytical and temporal
rules later.

Quarantine is a controlled data-quality outcome, not a failed command. The
command fails only when the batch identity is invalid, the raw batch is absent or
internally unreconciled, the transformation version is unsupported, existing
staging identity conflicts, or PostgreSQL cannot complete the transaction.

## Verification

Unit tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_staging.py tests/test_cli.py
```

Disposable PostgreSQL tests:

```powershell
$env:RUN_POSTGRES_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest `
  tests/test_raw_ingestion_postgres.py tests/test_staging_postgres.py -vv
Remove-Item Env:RUN_POSTGRES_TESTS
```

The PostgreSQL tests migrate uniquely named databases, force a mid-batch failure
to prove rollback, stage and replay clean synthetic rows, store malformed rows
with reasons, verify reconciliation, reject mutations, and drop only those exact
test databases.

## What CT-107 deliberately does not decide

- final modelling population or exclusion policy;
- modelling date window;
- canonical product taxonomy or label merges;
- language policy;
- global duplicate survivor;
- temporal split boundaries; or
- whether any quarantined record can be remediated.

Moving from Phase 1 ingestion into Phase 2 analytical dataset work requires a
separate explicit phase-gate approval.
