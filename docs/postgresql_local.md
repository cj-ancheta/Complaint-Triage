# Local PostgreSQL Guide

- Issue: CT-105
- Status: complete
- Prepared: 2026-07-22
- PostgreSQL image: `postgres:18.4-alpine3.23`
- Default address: `127.0.0.1:55432`

## Outcome

The repository now defines a reproducible, loopback-only PostgreSQL service with
a persistent named volume and a real health check. The service was started from
this checkout and verified with both `pg_isready` and SQL.

No application schema, migration, raw batch, complaint row, or model data was
created. The database currently contains zero user tables.

## Prerequisites

- Docker Desktop with Linux containers;
- Docker Compose v2 or later; and
- an available loopback port, defaulting to 55432.

Observed on this machine:

```text
Docker client: 29.5.3
Docker Compose: 5.1.4
Native psql: not installed
Native pg_isready: not installed
```

Docker Desktop must be running before Compose commands. On this machine, starting
Docker Desktop minimized allowed the Linux engine to remain available.

## First start

Create the ignored local environment file:

```powershell
Copy-Item .env.example .env
```

Replace `POSTGRES_PASSWORD=change-me-local-only` in `.env` with a unique local
development password. Do not reuse it for another system.

Validate the resolved Compose model without starting anything:

```powershell
docker compose config --quiet
```

Start PostgreSQL and wait for health:

```powershell
docker compose up -d --wait postgres
```

The first run downloads the pinned image and creates:

- network `complaint-triage-ml_default`;
- volume `complaint-triage-ml_postgres_data`; and
- service container `complaint-triage-ml-postgres-1`.

Compose-generated container names should not be referenced from application code.

## Readiness checks

Inspect service health and port binding:

```powershell
docker compose ps
docker compose port postgres 5432
```

Ask the server readiness utility inside the container:

```powershell
docker compose exec -T postgres sh -lc 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" -h 127.0.0.1 -p 5432'
```

Run a SQL identity and version probe:

```powershell
docker compose exec -T postgres psql -X --set ON_ERROR_STOP=1 `
  -U complaint_triage -d complaint_triage `
  -c "SELECT current_database(), current_user, current_setting('server_version'), current_setting('server_encoding');"
```

The explicit `ON_ERROR_STOP` prevents a SQL error from being mistaken for a
successful check.

## Verified evidence

The following was observed on 2026-07-22:

```text
Compose status: healthy
Published port: 127.0.0.1:55432 -> 5432/tcp
pg_isready: accepting connections
Database: complaint_triage
User: complaint_triage
Server version: 18.4
Server encoding: UTF8
Database collation/ctype: en_US.utf8
User table count: 0
Platform: linux/amd64
Second-container TCP without password: rejected
Second-container TCP with configured password: SELECT 1 succeeded
Compose down/up with volume retained: database restarted healthy
```

The image reported approximately 119.5 MB locally. This is environment evidence,
not a fixed cross-platform image-size claim.

## Connection settings for later issues

Host applications will use:

```text
host=127.0.0.1
port=55432
database=complaint_triage
user=complaint_triage
password=<value from ignored .env>
```

Illustrative DSN only:

```text
postgresql://complaint_triage:<password>@127.0.0.1:55432/complaint_triage
```

Do not commit a populated DSN. Do not put this database password in the Lovable
frontend or any `VITE_*` variable.

CT-105 deliberately did not add a Python PostgreSQL driver. The proposed CT-106
implementation now uses Psycopg for transactional loading and SQLAlchemy/Alembic
for ordered migrations; the rationale is recorded in ADR 0005.

## Lifecycle commands

Show status:

```powershell
docker compose ps
```

Stop without deleting data:

```powershell
docker compose stop postgres
```

Restart the existing service and wait for health:

```powershell
docker compose up -d --wait postgres
```

Remove the stopped container and network while retaining the named volume:

```powershell
docker compose down
```

Start it again from the retained volume:

```powershell
docker compose up -d --wait postgres
```

### Destructive cleanup

The following deletes the named PostgreSQL volume and all databases stored in it:

```powershell
docker compose down --volumes
```

Do not run it as routine cleanup. Resolve the exact Compose project and back up
meaningful data before any future destructive volume operation.

## Security boundary

Local controls:

- the host port binds only to `127.0.0.1`;
- password configuration is required;
- `.env` is ignored;
- no `POSTGRES_HOST_AUTH_METHOD=trust` override is configured;
- a separate-container TCP probe was rejected without a password and succeeded
  with the configured password;
- the container has `no-new-privileges`;
- no admin UI is exposed; and
- database data lives in a Docker-managed named volume.

Limitations:

- the configured role is a superuser inside this local-only database;
- the official image permits trusted local connections inside the same container,
  so `pg_isready` is a liveness/readiness signal rather than an authentication
  test;
- Docker Desktop and other local administrators can access the volume;
- the example password is intentionally public and must be replaced;
- there is no backup, encryption-at-rest, rotation, or production retention
  guarantee; and
- `pg_isready` does not prove migrations or application queries are correct.

## Troubleshooting

### Docker API pipe is unavailable

Symptom:

```text
failed to connect to the docker API ... dockerDesktopLinuxEngine
```

Start Docker Desktop, wait for the Linux engine, and rerun `docker info`. Do not
attempt Compose startup until `docker info` succeeds.

### Port 55432 is already in use

Choose another local port in ignored `.env`:

```text
POSTGRES_PORT=55433
```

Then rerun `docker compose up -d --wait postgres`. Update any local client DSN to
match.

### Password changes do not take effect

The official image initialization variables only apply to an empty data
directory. Changing `.env` does not rewrite roles inside an existing volume.
Use SQL role-management commands or deliberately recreate an expendable local
volume after confirming its exact project and backup needs.

### Container is unhealthy

Inspect status and logs without printing `.env`:

```powershell
docker compose ps
docker compose logs --tail 100 postgres
```

Do not paste logs publicly until they have been reviewed for connection strings
or future row-level data.

## CT-105 acceptance checklist

- [x] Docker and native PostgreSQL tooling audited.
- [x] Supported PostgreSQL version verified from primary sources.
- [x] Exact official image tag selected.
- [x] Loopback-only port and named volume configured.
- [x] Environment-provided password required.
- [x] `pg_isready` health check configured.
- [x] Compose model validates.
- [x] Real service starts and reports healthy.
- [x] Readiness and SQL identity/version probes pass.
- [x] Network password behavior verified from a second container.
- [x] Non-destructive down/up cycle preserves and reuses the named volume.
- [x] Zero application tables confirmed.
- [x] Lifecycle and destructive cleanup boundaries documented.
- [x] No ingestion or schema migration implemented.
- [x] User approved the ADR and CT-105 diff on 2026-07-22.

## CT-106 follow-up

CT-106 now proposes append-only raw ingestion with batch metadata and a disposable
database test. It remains synthetic-only. Before any real response is retained,
the open raw-artifact and database-row retention policy from CT-104 must be
approved separately.
