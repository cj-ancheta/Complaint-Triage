# ADR 0004: Run Local PostgreSQL with Docker Compose

- Status: accepted
- Date: 2026-07-22
- Accepted: 2026-07-22
- Issue: CT-105

## Context

The project needs PostgreSQL for raw, staging, analytical, prediction, and review
data in later issues. The current Windows machine has Docker 29.5.3 and Docker
Compose 5.1.4 installed, but no native `psql`, `pg_isready`, or PostgreSQL Windows
service. A native installation would add machine-specific configuration and make
clean-checkout reproduction harder.

As of 2026-07-22, PostgreSQL 18.4 is the current 18.x minor and PostgreSQL 18 is
supported through November 2030. The Docker Official Image publishes the exact
`18.4-alpine3.23` tag.

Sources:

- <https://www.postgresql.org/support/versioning/>
- <https://hub.docker.com/_/postgres>
- <https://hub.docker.com/_/postgres/tags>

## Decision

Run one local PostgreSQL service through `compose.yaml` using:

- Docker Official Image `postgres:18.4-alpine3.23`;
- an exact database minor and Alpine base tag rather than `latest`;
- a named Docker volume mounted at `/var/lib/postgresql`;
- PostgreSQL 18 `PGDATA` at `/var/lib/postgresql/18/docker`;
- host binding only on `127.0.0.1`, with default host port `55432`;
- required database, user, and password values from the ignored `.env` file;
- no `trust` authentication override;
- a `pg_isready` health check;
- `no-new-privileges`; and
- no database administration UI or additional container.

The official image's `POSTGRES_USER` is a database superuser. This is accepted
only for the isolated local-development service. A deployed service must use
separate migration and least-privilege application roles through a later ADR.
The image permits trusted connections originating inside the same container, but
a second-container TCP probe confirms that network access requires the configured
password.

Database health in CT-105 means PostgreSQL accepts a connection to the configured
database. It does not imply that application migrations, tables, ingestion, or
model-serving dependencies are ready.

## Consequences

Benefits:

- a consistent PostgreSQL version across machines;
- no native Windows database installation;
- health and lifecycle commands are reproducible;
- loopback-only host exposure;
- persistent local data without bind-mount path permissions; and
- easy non-destructive stop and restart.

Costs:

- Docker Desktop must be running;
- the first start downloads an image of roughly 120 MB on this platform;
- the named volume consumes local disk until explicitly deleted;
- Alpine may require extra work if a future native extension is unavailable in
  the base image; and
- exact minor tags require deliberate security/minor-version updates.

## Alternatives considered

### Native PostgreSQL on Windows

Rejected for the initial local path because no native server or client is
installed, setup is more machine-specific, and service cleanup is less isolated.

### SQLite

Rejected because later ingestion and SQL work are intended to demonstrate
PostgreSQL behavior, migrations, schemas, and production-relevant types.

### PostgreSQL `latest`

Rejected because an implicit major upgrade can make an existing data volume
unstartable and invalidate reproducibility.

### Cloud database

Deferred. It would add credentials, cost, networking, and retention decisions
before the local pipeline exists.

### Add pgAdmin or Adminer

Rejected for CT-105. `psql` inside the database container is sufficient for
readiness and learning, and another exposed service adds no exit evidence.

## Version-update policy

Review the PostgreSQL version at least quarterly and before any public
deployment. Minor-version changes require:

1. reviewing PostgreSQL release notes;
2. updating the exact image tag;
3. backing up any meaningful local volume;
4. rerunning Compose validation and database tests; and
5. recording the change.

A PostgreSQL major upgrade requires a new ADR and an explicit data migration or
volume-recreation plan.

## Revisit triggers

Create or amend an ADR before:

- deploying PostgreSQL outside local development;
- adding separate database roles or network clients;
- changing the major version;
- adding extensions that make Alpine unsuitable;
- using bind mounts or remote volumes;
- introducing backups or retention guarantees; or
- placing the database on a non-loopback interface.
