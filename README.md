# Responsible AI Complaint Triage

An educational portfolio project exploring how a human-in-the-loop NLP system can suggest product routes for financial complaint narratives, abstain when uncertain, and expose the evidence and controls needed for responsible review.

## Current status

**Phase 2 is active; CT-205 is accepted and CT-206 is in review.**

The repository includes privacy-safe CFPB source and taxonomy profilers with
mocked network and contract tests. On 22 July 2026, the aggregate-only taxonomy
command successfully measured the current-form transition without requesting,
logging, or persisting complaint rows or narratives. ADR 0007 accepts the eleven
August 2023 form labels and a September 2023 through December 2024 window. The
accepted raw, staging, population, and temporal-split layers have processed the
locally retained real run. Source narratives remain governed local data; only
closed aggregate evidence is commit-safe. Any model metric must come from a
versioned evaluation artifact before it appears here or in the portfolio.

CT-202 implements an accepted, append-only eligibility report over staged
rows. It applies the accepted taxonomy/window, identifies English narratives
offline, records closed exclusion reasons and length metadata, and never copies
narratives into the analytical schema. Current report evidence is synthetic only.
ADR 0009 authorizes local retention for the first real extract through 19
November 2026. CT-108 provides accepted manifest-level retention enforcement;
CT-109 provides an accepted synthetic-tested monthly writer and cleanup
workflow. CT-110's first retained real run and aggregate population evidence are
accepted as pipeline evidence; no model has been trained and no metric is
approved as a portfolio claim. CT-203's reconciled temporal split and normalized
duplicate-isolation evidence are accepted as pipeline evidence.
CT-204's training-only majority reference baseline is accepted as issue
evidence; no model metric is approved as a portfolio claim.
ADR 0011 accepts CT-205's fixed train-only TF-IDF representation, four logistic
candidates, validation-only selection rule, untouched-test boundary, and
local-only fitted artifact. Real CT-205 training evidence is not yet accepted.
The accepted validation-only run selected the converged `c1p0-unweighted`
candidate. Its aggregate issue evidence is accepted; test remains untouched and
no metric has been approved as a public portfolio claim.

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
- [CFPB taxonomy stability profile](docs/cfpb_taxonomy_stability.md)
- [Accepted taxonomy and modelling-window ADR](docs/decisions/0007-proposed-taxonomy-window.md)
- [Analytical population report](docs/analytical_population.md)
- [Accepted analytical-population ADR](docs/decisions/0008-proposed-analytical-population.md)
- [Local real-data retention ADR](docs/decisions/0009-local-real-data-retention.md)
- [Retention-controlled real extraction plan](docs/real_extraction_plan.md)
- [Monthly extraction and cleanup operator guide](docs/real_extraction.md)
- [CT-110 live-run record](docs/ct110_live_run.md)
- [Temporal split and duplicate isolation](docs/temporal_split.md)
- [Majority reference baseline](docs/majority_baseline.md)
- [TF-IDF logistic-regression baseline](docs/tfidf_logreg.md)
- [Validation-only baseline error analysis](docs/baseline_error_analysis.md)
- [Accepted temporal split ADR](docs/decisions/0010-temporal-split-duplicate-isolation.md)
- [Accepted TF-IDF selection ADR](docs/decisions/0011-tfidf-logreg-validation-selection.md)
- [Architecture](docs/architecture.md)
- [Learning log](docs/learning_log.md)

Cleanup inventory is dry-run-only unless the exact run ID is supplied with
`--execute`:

```powershell
complaint-triage cleanup-real-data --run-manifest data/manifests/cfpb/runs/<run-id>.json
```

The live adapter additionally requires a clean commit, 20 GiB free, a fresh
aggregate-only preflight, and the exact retention policy confirmation:

```powershell
complaint-triage acquire-real-run --confirmation cfpb-local-120d-v1
```

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

Run the aggregate-only taxonomy profiler:

```powershell
.\.venv\Scripts\python.exe -m complaint_triage profile-taxonomy
```

Create an aggregate analytical-population report for a staged batch:

```powershell
.\.venv\Scripts\python.exe -m complaint_triage report-population `
  --batch-id cfpb-YYYYMMDDTHHMMSSZ-aaaaaaaaaaaa
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
raw acquisition stays unavailable until CT-109 implements the approved ADR 0009
streaming and cleanup controls.

## License

No open-source license has been selected. All rights are reserved until that decision is made deliberately.
