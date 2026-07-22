# Append-only raw ingestion

CT-106 turns an already-created CFPB raw batch into a validated, append-only
PostgreSQL record. It does not call the CFPB endpoint and currently refuses every
non-synthetic manifest.

## Mental model

```text
tracked manifest ─┐
                  ├─ validate lineage and reconcile ─ transaction ─ raw schema
ignored artifact ─┘                                  ├─ ingestion_batches
                                                     └─ complaints
```

The manifest is safe metadata. The content-addressed artifact contains source
rows and stays under ignored `data/raw/`. PostgreSQL retains the source-aligned
payload locally so later staging work can be reproduced. Normal command output
contains only batch identities, checksums, counts, status, and privacy flags.

## Configuration

Copy `.env.example` to ignored `.env` and change the local-only example password.
The application reads these names:

| Name | Purpose | Local default |
|---|---|---|
| `POSTGRES_DB` | database name | required |
| `POSTGRES_USER` | database role | required |
| `POSTGRES_PASSWORD` | database password | required |
| `POSTGRES_HOST` | server host | `127.0.0.1` |
| `POSTGRES_PORT` | published server port | `55432` |

Process environment values override `.env`. Passwords are bound through driver
configuration and redacted from the settings representation. Do not commit
`.env` or paste connection strings into tickets or screenshots.

## Start and migrate PostgreSQL

From the repository root:

```powershell
docker compose up -d --wait postgres
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

The first migration creates `raw.ingestion_batches`, `raw.complaints`, their
constraints and index, and mutation-rejection triggers. Alembic records the
applied revision in `alembic_version`.

`alembic downgrade base` intentionally drops the complete `raw` schema and its
data. Treat that command as destructive and use it only against a disposable
database.

## Rehearse with the synthetic fixture

The fixture is tracked under `tests/fixtures/cfpb`. Its manifest expects the raw
bytes at the content-addressed path declared in `artifact.relative_path`. For a
manual rehearsal, copy—not move—the files:

```powershell
$manifest = Get-Content tests/fixtures/cfpb/raw_batch_manifest_synthetic.json | ConvertFrom-Json
$artifactPath = Join-Path (Get-Location) $manifest.artifact.relative_path
New-Item -ItemType Directory -Force (Split-Path $artifactPath) | Out-Null
New-Item -ItemType Directory -Force data/manifests/cfpb | Out-Null
Copy-Item tests/fixtures/cfpb/search_response_synthetic.json $artifactPath
Copy-Item tests/fixtures/cfpb/raw_batch_manifest_synthetic.json data/manifests/cfpb/synthetic.json
.\.venv\Scripts\python.exe -m complaint_triage ingest-raw-batch `
  --manifest data/manifests/cfpb/synthetic.json
```

The first run reports `status: inserted` and three inserted records. Repeating the
same command reports `status: already_ingested` and zero inserted records. These
statuses describe database writes, not source acquisition.

The copied artifact remains ignored by Git. The copied manifest is eligible for
tracking because its contract contains no row values, but it is only a rehearsal
copy and does not need to be committed.

## Validation and failure behavior

The loader refuses a batch before connecting when any of these disagree:

- manifest JSON Schema or controlled path;
- exact stored byte count and SHA-256;
- content-addressed artifact path;
- canonical request fingerprint;
- retrieval-time/artifact-derived batch ID;
- response metadata and hit totals;
- returned, unique, duplicate, or narrative counts;
- observed dates, fields, or complaint-ID types;
- explicit synthetic fixture markers.

All database writes occur in one transaction. A failed complaint insert removes
the preceding batch insert automatically. Database exceptions become the generic
code `database_write_failed`; raw driver text and payload values are not printed.

## Run the tests

Unit checks do not require a database:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_db.py tests/test_raw_ingestion.py tests/test_cli.py
```

The integration check creates a uniquely named disposable database, applies the
migration, proves forced rollback, loads and replays the fixture, tests the raw
mutation triggers, then drops that exact database:

```powershell
$env:RUN_POSTGRES_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests/test_raw_ingestion_postgres.py -vv
Remove-Item Env:RUN_POSTGRES_TESTS
```

CI runs this test against its own ephemeral PostgreSQL service. The committed CI
credential is intentionally scoped to that disposable runner and is not a
deployment secret.

## Current boundary and next decision

Real CFPB manifests return `real_data_retention_policy_unapproved` even when they
are otherwise valid. Before that changes, the project must approve and document:

- which real artifacts and database rows are retained;
- the retention duration and start event;
- the deletion owner, command, verification, and audit evidence;
- backup and derived-data behavior; and
- how local development differs from a future deployed environment.

The proposed CT-107 staging behavior uses only synthetic raw rows and does not
cross that decision gate. See `docs/staging_transformations.md`.
