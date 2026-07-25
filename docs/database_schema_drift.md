# Database schema drift control

Status: QA-107 accepted; GitHub Actions run 30163564539 passed

`complaint_triage.database_schema.metadata` is the authoritative SQLAlchemy
model for the eight governed tables in the `raw`, `staging`, and `analytical`
schemas. Alembic migrations remain the ordered change history. They are
deliberately separate artifacts: changing metadata without a migration must
make `alembic check` fail, while adding a migration without updating metadata
must also leave a reviewable mismatch.

Both runtime CI jobs start from an empty disposable PostgreSQL instance, run
`alembic upgrade head`, then run `alembic check` with `include_schemas=True`.
This proves the complete upgrade chain and compares the resulting database with
the authoritative metadata before tests execute. PostgreSQL functions and
append-only triggers are migration-managed objects outside Alembic's ordinary
table autogeneration; their behavior remains protected by integration tests.

## Local verification

Start the loopback-only Compose database and use the values from ignored local
`.env` configuration:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pytest tests/test_database_schema.py `
  tests/test_raw_ingestion_postgres.py tests/test_staging_postgres.py `
  tests/test_analytical_population_postgres.py tests/test_temporal_split_postgres.py -q
```

Expected output includes revision `0004_temporal_split (head)` and `No new
upgrade operations detected.` Never use autogenerate output as an unattended
migration: review names, schemas, constraints, defaults, indexes, functions,
triggers, downgrade behavior, and data-transition implications first.

GitHub Actions run
[`30163564539`](https://github.com/cj-ancheta/Complaint-Triage/actions/runs/30163564539)
passed both empty-database upgrade/check sequences plus `security` on commit
`6c885caa9eb33618778d81c4e60929cc0eee0c4a`.
