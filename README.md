# Responsible AI Complaint Triage

An educational portfolio project exploring how a human-in-the-loop NLP system can suggest product routes for financial complaint narratives, abstain when uncertain, and expose the evidence and controls needed for responsible review.

## Current status

**Phase 1 ingestion is complete; the Phase 2 transition awaits approval.**

The repository now includes a privacy-safe, five-record CFPB source profiler with
mocked network and contract tests. The live endpoint remains inaccessible from
this execution environment, so a successful deployed response check is still
outstanding. A versioned raw-batch manifest and exact-byte SHA-256 contract are
approved, and a loopback-only PostgreSQL 18.4 service now passes real health and
SQL readiness checks. The accepted CT-106 migration and loader validate and load
the three-record synthetic fixture atomically, reject replays and mutations, and
unconditionally block real data while retention remains undecided. No real source
data has been ingested. The accepted CT-107 staging layer assigns every raw row a
versioned accepted or quarantined outcome without selecting a modelling taxonomy
or population. No model has been trained. Any future metric must be generated
from a versioned evaluation artifact before it appears here or in the portfolio.

## Intended use

The proposed system is a decision-support demonstration for complaint-routing operations. It will suggest a product category and confidence score, abstain below an approved threshold, and allow a human reviewer to accept, correct, or escalate the suggestion.

## Non-goals

This project will not:

- determine whether a complaint is truthful;
- assess legal liability or compensation;
- close, reject, or answer complaints automatically;
- infer protected characteristics;
- claim demographic fairness without suitable evidence;
- retain arbitrary public-demo narratives without a justified policy; or
- use model complexity as a substitute for measured utility.

## Source of truth

- [Full project specification](SPEC.md)
- [Controlled AI-assisted workflow](WORKFLOW.md)
- [Implementation backlog](BACKLOG.md)
- [Phase 0 review and open decisions](docs/phase_0_review.md)
- [CFPB source inventory](docs/cfpb_source_inventory.md)
- [CFPB bounded profile contract](docs/cfpb_bounded_profile_plan.md)
- [CFPB profiling command](docs/cfpb_profile_command.md)
- [CFPB raw batch manifest](docs/cfpb_raw_batch_manifest.md)
- [Raw batch JSON Schema](contracts/cfpb-raw-batch-manifest.schema.json)
- [Local PostgreSQL guide](docs/postgresql_local.md)
- [Append-only raw ingestion guide](docs/raw_ingestion.md)
- [Versioned staging transformation guide](docs/staging_transformations.md)
- [Architecture](docs/architecture.md)
- [Learning log](docs/learning_log.md)

Future coding agents must also read [AGENTS.md](AGENTS.md) before making changes.

## Local setup

The repository currently supports Python 3.12 and 3.13. The local machine has Python 3.13 available.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run validation:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
```

Run the bounded source-contract profiler:

```powershell
.\.venv\Scripts\python.exe -m complaint_triage profile-cfpb
```

Start the local PostgreSQL service after copying `.env.example` to ignored
`.env` and replacing its example password:

```powershell
docker compose up -d --wait postgres
.\.venv\Scripts\python.exe -m alembic upgrade head
```

## Repository boundary

This repository will contain the Python ingestion, SQL, modelling, evaluation, FastAPI service, tests, and governance documentation.

The Lovable React interface will live in a separate `complaint-triage-web` repository and consume a versioned HTTP API. This prevents frontend generation from changing the model pipeline or exposing server-side secrets.

## Data and privacy

The planned source is the public CFPB Consumer Complaint Database. Raw complaint
narratives, generated model artifacts, secrets, and local experiment stores are
excluded from Git. CT-106 can load only explicit synthetic fixture batches; real
raw ingestion stays disabled until a retention policy is approved.

## License

No open-source license has been selected. All rights are reserved until that decision is made deliberately.
