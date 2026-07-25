# Responsible AI Complaint Triage

An educational portfolio project exploring how a human-in-the-loop NLP system can suggest product routes for financial complaint narratives, abstain when uncertain, and expose the evidence and controls needed for responsible review.

## Current status

**Phase 4 governance is complete with a manual-review-only release decision.**

The accepted local research run now covers bounded acquisition, append-only raw
and staging layers, an English analytical population, normalized duplicate
isolation, temporal splits, majority and TF-IDF references, compact MiniLM
training, model comparison, probability calibration, CPU utility assessment,
and a fixed abstention-policy analysis.

Calibrated MiniLM is the selected research candidate, but no confidence
threshold passed every approved global and class-aware gate. The accepted
system state is therefore `manual_review_only`: automated routing, frozen-test
access, API/web deployment, and public metric promotion are not authorized.
This is a governance outcome, not a production-performance claim.

Source narratives and model artifacts remain governed local data. Only closed,
aggregate, hash-traced evidence is commit-safe. Start with the
[governance pack](docs/governance_pack.md) for the release decision, model card,
data sheet, risks, oversight policy, security boundary, and evidence lineage.

## Intended use

The research goal is a decision-support demonstration for complaint-routing
operations. A future approved system could show a product suggestion and
confidence, abstain under an approved policy, and let a human reviewer accept,
correct, or escalate it. The current model has no approved threshold, so every
case remains manual and no suggestion interface is authorized.

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
- [Governance pack and release decision](docs/governance_pack.md)
- [Model card](docs/model_card.md)
- [Dataset sheet](docs/data_sheet.md)
- [Risk register](docs/risk_register.md)
- [Human oversight policy](docs/human_oversight.md)
- [Security assessment](docs/security.md)
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
- [Transformer tokenizer profile](docs/transformer_token_profile.md)
- [Transformer dataset pipeline](docs/transformer_dataset.md)
- [MiniLM training and validation selection](docs/transformer_training.md)
- [Accepted temporal split ADR](docs/decisions/0010-temporal-split-duplicate-isolation.md)
- [Accepted TF-IDF selection ADR](docs/decisions/0011-tfidf-logreg-validation-selection.md)
- [Architecture](docs/architecture.md)
- [Required CI profiles](docs/ci.md)
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

The repository uses a locked Python 3.13 standard environment and a separate
locked Python 3.12 transformer environment. See the
[reproducible-environment guide](docs/reproducible_environments.md) and
[ADR 0017](docs/decisions/0017-pip-compatible-hashed-locks.md).

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/locks/bootstrap.lock.txt
.\.venv\Scripts\python.exe -m pip install --require-hashes `
  -r requirements/locks/standard-py313-win-amd64.lock.txt
.\.venv\Scripts\python.exe -m pip install `
  --no-deps --no-build-isolation -e .
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

The source is the public CFPB Consumer Complaint Database. Raw complaint
narratives, generated model artifacts, secrets, and local experiment stores are
excluded from Git. The retained real run is permitted only on the local machine
and loopback PostgreSQL volume under ADR 0009, with an absolute deletion deadline
of 19 November 2026. Aggregate reports and governance evidence contain no
narratives, complaint IDs, or row-level predictions.

## License

No open-source license has been selected. All rights are reserved until that decision is made deliberately.
