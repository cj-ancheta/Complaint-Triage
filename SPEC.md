# Project 1: Responsible AI Complaint Triage Platform

## Purpose of this document

This is the build specification, learning guide, and delivery checklist for a portfolio project aimed primarily at the PERSOL/JobStreet AI Data Analyst role.

The project is deliberately designed to demonstrate more than model training. It should prove that Charles can:

- turn an ambiguous regulated-domain problem into a bounded AI use case;
- ingest and model real public data with Python and SQL;
- compare a classical baseline with a deep-learning model;
- expose a model through a tested API;
- build a credible human-review workflow;
- monitor data and model behaviour;
- document limitations, governance, security, and operational controls; and
- use AI-assisted coding without surrendering technical understanding.

This is the first project to build.

---

## 1. Working title and portfolio summary

### Working title

**Responsible AI: Human-in-the-Loop Complaint Triage**

### One-sentence portfolio summary

An end-to-end NLP system that routes financial complaint narratives, abstains when uncertain, and gives reviewers the evidence and controls needed to supervise model decisions.

### Target portfolio disciplines

- Natural language processing
- Deep learning
- MLOps
- Responsible AI
- RegTech
- Data engineering

### Intended role alignment

Primary target:

- PERSOL/JobStreet `[ENTRY] AI Data Analyst`

Secondary signals:

- EY Tax Technology and Transformation: governed data, requirements, testing, documentation, and stakeholder-oriented delivery
- Holdex Data Scientist: Python, SQL, full ML lifecycle, technical writing, and self-directed execution

---

## 2. Business problem

Financial regulators and regulated organisations receive large volumes of free-text complaints. A human operations team must determine which product or issue team should review each complaint.

Manual routing is slow and inconsistent. Fully automated routing is also risky because:

- complaint language can be ambiguous;
- taxonomies change;
- uncommon complaints may be the most important;
- a confident-looking model can still be wrong;
- the source data is not representative of every consumer; and
- a routing error may delay a response to a vulnerable person.

The system will therefore operate as a **decision-support tool**, not an autonomous decision-maker.

For every narrative, it should:

1. predict a complaint product category;
2. provide a calibrated confidence score;
3. abstain and send the case to manual review when confidence is insufficient;
4. display a concise explanation and relevant model metadata;
5. let a reviewer accept, correct, or escalate the suggestion; and
6. record review outcomes for future evaluation.

### Explicit non-goals

The first release will not:

- determine whether a complaint is truthful;
- assess legal liability;
- calculate consumer compensation;
- infer protected characteristics;
- automatically close or reject complaints;
- generate responses to consumers;
- rank people by perceived vulnerability;
- claim demographic fairness without suitable data; or
- use an LLM merely to make the project look current.

These boundaries are important evidence of responsible problem framing.

---

## 3. Primary users and user stories

### Primary user: complaint operations reviewer

As a reviewer, I want a suggested route with a confidence level so that I can process routine cases faster without losing control over uncertain cases.

As a reviewer, I want to see why the system abstained so that I understand what requires manual judgement.

As a reviewer, I want to correct a suggestion so that routing errors are captured rather than hidden.

### Secondary user: model owner

As a model owner, I want to inspect performance by time period and product class so that aggregate accuracy does not conceal weak segments.

As a model owner, I want drift and data-quality alerts so that I can detect when the operating environment changes.

As a model owner, I want every model version linked to its data snapshot, code revision, evaluation report, and approval status.

### Secondary user: governance or risk reviewer

As a governance reviewer, I want a model card, risk register, test evidence, and human-oversight policy so that I can evaluate whether deployment claims are justified.

---

## 4. Source data

### Primary source

Use the official Consumer Financial Protection Bureau Consumer Complaint Database:

- Portal: <https://www.consumerfinance.gov/data-research/consumer-complaints/>
- API documentation: linked from the official portal
- Available formats: API, CSV, and JSON
- Update pattern: generally daily

Useful fields may include:

- complaint ID;
- date received;
- product and sub-product;
- issue and sub-issue;
- consumer complaint narrative;
- submission channel;
- state and ZIP code;
- company;
- company response;
- timely response indicator; and
- date sent to company.

The exact schema must be recorded from the source at ingestion time instead of assumed from this document.

### Mandatory source limitations

The project documentation must state that:

- the database is not a statistical sample of all consumer experiences;
- complaint volume cannot be interpreted as company harm without exposure or market-share context;
- narratives are published only when consumers opt in and after personal-information processing;
- recent records may have incomplete narrative coverage;
- consumers select categories under the form taxonomy available at submission time; and
- taxonomy changes can produce label drift.

### Initial modelling subset

Start with narratives that:

- are non-null and non-empty;
- have a product label;
- fall within a declared time window;
- use a stable product taxonomy; and
- are written in English, unless multilingual work is deliberately added later.

Do not begin with the entire database. Use a bounded sample for iteration, then test the pipeline at a larger scale after correctness is established.

### Data-version record

Every training run must record:

- source URL or API query;
- extraction timestamp in UTC;
- minimum and maximum complaint dates;
- raw row count;
- filtered row count;
- narrative coverage;
- class distribution;
- checksum or data-version identifier; and
- transformation-code commit.

Raw personal narratives must not be committed to GitHub.

---

## 5. Proposed architecture

```text
CFPB API / export
        |
        v
Python ingestion job
        |
        +--> immutable raw files outside Git
        |
        v
PostgreSQL
  raw -> staging -> analytical tables
        |
        v
Feature and split pipeline
        |
        +--> TF-IDF + Logistic Regression baseline
        |
        +--> DistilBERT or MiniLM classifier in PyTorch
        |
        v
Evaluation + calibration + abstention policy
        |
        v
Versioned model artifact / MLflow run
        |
        v
FastAPI inference service
        |
        +--> prediction endpoint
        +--> health/readiness endpoints
        +--> model metadata endpoint
        +--> review feedback endpoint
        |
        v
Lovable React application
  reviewer queue + case detail + monitoring views
```

### Recommended repository arrangement

Use two repositories because Lovable creates and owns its GitHub-connected frontend repository:

```text
complaint-triage-ml/
  Python pipeline, SQL, model, FastAPI, tests, and documentation

complaint-triage-web/
  Lovable-generated React frontend, UI tests, and API client
```

The current Lovable GitHub workflow can export a Lovable project to GitHub and synchronize the default branch in both directions. It does not currently import an arbitrary existing GitHub repository into a new Lovable project. Therefore:

1. create the frontend project in Lovable;
2. connect it to the correct GitHub account and repository early;
3. do not rename, move, or delete that repository while it is connected;
4. keep the ML backend in its own normal repository; and
5. connect the two through a documented HTTP API.

Lovable documentation:

- GitHub: <https://docs.lovable.dev/integrations/github>
- External APIs: <https://docs.lovable.dev/integrations/introduction>
- Supabase: <https://docs.lovable.dev/integrations/supabase>
- Publishing: <https://docs.lovable.dev/features/publish>

---

## 6. Technology choices

### Python and data

- Python 3.12 or another currently supported version
- `uv` or Poetry for deterministic dependency management
- pandas or Polars for local transformations
- SQLAlchemy and Alembic for database access and migrations
- PostgreSQL
- Pydantic for data contracts
- Jupyter only for exploration, not as the production pipeline

### Modelling

- scikit-learn for the baseline
- PyTorch and Hugging Face Transformers for deep learning
- MLflow for experiment and artifact tracking
- joblib or a documented model serialization format for the baseline

### API and operations

- FastAPI
- Uvicorn
- Docker and Docker Compose
- structured JSON logging
- Ruff for linting and formatting
- mypy or Pyright for selected type checking
- pytest and coverage reporting
- GitHub Actions

### Monitoring

Use lightweight, understandable tools. Possible options include:

- Evidently for drift and performance reports;
- custom SQL metrics and a small monitoring endpoint; or
- a combination of both.

Do not add orchestration platforms, Kubernetes, or cloud services until the local end-to-end path works.

### Web interface

- Lovable-generated React and TypeScript application
- a deliberate component system rather than a generic dashboard template
- TanStack Query or the existing Lovable data-fetching pattern
- accessible charts and tables
- a typed API client generated from, or checked against, the FastAPI OpenAPI schema

---

## 7. Lovable feasibility and integration design

### Is Lovable suitable?

Yes. Lovable can create and publish the reviewer-facing web application, synchronize its code to GitHub, connect to Supabase, and call external APIs.

It should not be responsible for:

- training the NLP model;
- running a large PyTorch model inside a browser;
- storing model credentials in frontend environment variables;
- replacing the Python evaluation pipeline; or
- manufacturing model metrics in the UI.

### Integration option A: direct public API

Use this for the first portfolio MVP if the prediction service is intentionally public and read-only.

Requirements:

- enable CORS only for the Lovable app domain and local development origin;
- reject oversized inputs;
- apply rate limits;
- do not store submitted text by default;
- never expose infrastructure secrets;
- return stable, versioned response objects; and
- provide a demo/example mode if the backend is asleep or unavailable.

### Integration option B: protected API through an Edge Function

Use this when the Python API requires a secret token.

```text
Browser
  -> Lovable Cloud or Supabase Edge Function
       -> secret server-side API token
       -> external FastAPI model service
```

This prevents a backend token from being included in browser JavaScript. The Edge Function is a proxy and policy boundary. It is not the place to run the PyTorch model.

### Suggested API contract

#### `POST /v1/predictions`

Request:

```json
{
  "narrative": "The consumer complaint text goes here.",
  "request_id": "client-generated-uuid"
}
```

Response:

```json
{
  "request_id": "client-generated-uuid",
  "model_version": "complaint-router-0.1.0",
  "taxonomy_version": "cfpb-product-YYYY-MM",
  "predicted_product": "Credit reporting or other personal consumer reports",
  "confidence": 0.87,
  "decision": "suggest",
  "alternatives": [
    {"label": "Debt collection", "confidence": 0.08},
    {"label": "Credit card", "confidence": 0.03}
  ],
  "reason_codes": ["credit-report terms", "dispute language"],
  "warnings": [],
  "latency_ms": 94
}
```

When confidence is below the operating threshold:

```json
{
  "decision": "abstain",
  "predicted_product": null,
  "confidence": 0.42,
  "warnings": ["Confidence below the approved routing threshold"]
}
```

#### Other endpoints

- `GET /health`: process is alive
- `GET /ready`: model and required dependencies are ready
- `GET /v1/model-info`: model card summary, version, classes, threshold, and training date
- `POST /v1/reviews`: optional reviewer outcome; must have a documented retention policy
- `GET /v1/demo-cases`: curated, non-sensitive examples for the public interface

Generate the final OpenAPI schema from code and treat it as the authoritative contract.

### Frontend pages

#### 1. Overview

- problem statement;
- system boundary;
- current model version;
- evaluation-period summary;
- prominent statement that the system supports rather than replaces reviewers; and
- link to methodology and limitations.

#### 2. Review workspace

- narrative input or curated demo-case selector;
- suggested route;
- confidence and abstention state;
- top alternatives;
- reason codes or explanation;
- model version;
- accept, correct, and escalate controls; and
- clear loading, empty, success, and failure states.

#### 3. Model performance

- baseline versus transformer comparison;
- per-class precision, recall, and F1;
- confusion matrix;
- calibration plot;
- coverage-versus-accuracy chart for abstention thresholds;
- latency and model-size comparison; and
- temporal test-window label.

#### 4. Monitoring

- recent input-volume trend;
- class-distribution drift;
- narrative-length drift;
- missing or rejected input counts;
- review correction rate when feedback data exists; and
- alert states with explanations.

#### 5. Governance

- intended use and prohibited use;
- data limitations;
- human-oversight policy;
- risk register summary;
- security controls;
- model change log; and
- links to the full GitHub documentation.

### Visual direction for Lovable

The interface should feel like a calm regulatory operations tool:

- warm off-white or deep charcoal background;
- one restrained blue or sage signal colour;
- readable sans-serif type with monospaced metadata;
- square or lightly rounded panels;
- minimal decoration;
- charts selected for decisions, not dashboard density;
- confidence expressed with text and numbers, never colour alone;
- abstention treated as a valid controlled outcome, not an error; and
- no glowing AI gradients, robots, neural-network illustrations, or fake live activity.

---

## 8. Data model

The exact schema may evolve, but the conceptual layers should remain explicit.

### Raw layer

`raw_complaints`

- source payload or source-aligned columns;
- extraction batch ID;
- extraction timestamp;
- source schema version;
- source-record checksum.

Raw rows should be append-only where practical.

### Staging layer

`stg_complaints`

- normalized dates;
- normalized nulls;
- canonical product labels;
- basic narrative-quality flags;
- deduplication status;
- exclusion reason.

### Analytical layer

`ml_complaints`

- complaint ID;
- received date;
- narrative;
- target product;
- split assignment;
- taxonomy version;
- transformation version.

`model_predictions`

- prediction ID;
- request ID;
- timestamp;
- model version;
- predicted label;
- confidence;
- decision;
- latency;
- input metadata that does not reproduce sensitive text.

`review_outcomes`

- review ID;
- prediction ID;
- action;
- corrected label if supplied;
- timestamp;
- optional reason code.

For a public portfolio deployment, avoid retaining arbitrary user-entered narratives. Store only curated demo IDs or aggregate metadata unless there is a justified, disclosed purpose.

---

## 9. Data preparation and leakage controls

### Required checks

- unique complaint IDs;
- valid receipt dates;
- non-empty narratives;
- target-label membership in the declared taxonomy;
- duplicate and near-duplicate narratives;
- class counts before and after filtering;
- date coverage;
- unexpected source-schema changes;
- language distribution; and
- narrative-length distribution.

### Temporal splitting

Use a temporal split rather than a random split.

Example only:

- training: earliest 70% of time;
- validation: following 15%;
- test: latest 15%.

Final date boundaries must be chosen after inspecting coverage and taxonomy changes.

Why:

- it better represents future deployment;
- it exposes taxonomy and language drift;
- it prevents near-future observations from influencing earlier evaluation; and
- it makes retraining decisions meaningful.

### Duplicate controls

Exact duplicates must not cross splits. Consider perceptual hashing or similarity checks for templated narratives. Document the chosen method and its limitations.

### Feature restrictions

The narrative is the primary model input. Do not include company, state, ZIP code, response outcome, or post-routing fields merely because they improve a metric.

Each feature must pass two questions:

1. Would it be available at the actual routing decision time?
2. Is its use appropriate and necessary for this routing purpose?

---

## 10. Modelling plan

### Baseline 0: majority and rule baselines

Record:

- majority-class performance;
- simple keyword/rule performance if implemented; and
- class distribution.

This prevents the ML results from being presented without context.

### Baseline 1: TF-IDF plus logistic regression

Suggested components:

- word and/or character n-grams;
- minimum document frequency;
- class weighting if justified;
- multinomial logistic regression;
- hyperparameter search limited to a declared validation set; and
- probability calibration if raw probabilities are inadequate.

Benefits:

- fast training;
- interpretable features;
- strong text-classification baseline;
- low inference cost; and
- useful benchmark against deep learning.

### Candidate 2: compact transformer

Start with DistilBERT or another compact English encoder rather than a very large model.

Required controls:

- fixed random seeds where supported;
- declared maximum token length;
- token truncation analysis;
- class weighting or sampling decision;
- early stopping;
- saved training configuration;
- validation-only tuning;
- test set touched once for final comparison; and
- CPU inference measurement if the public deployment uses CPU.

### Model-selection rule

Do not assume the transformer wins.

Select the final operational model using a written utility decision covering:

- macro-F1;
- worst-class recall;
- calibration;
- selective accuracy after abstention;
- latency;
- memory footprint;
- explainability;
- operational complexity; and
- deployment cost.

It is acceptable, and potentially impressive, to deploy the logistic-regression model if its practical utility is better.

---

## 11. Evaluation plan

### Core metrics

- macro-F1 as the main balanced classification metric;
- per-class precision, recall, and F1;
- weighted-F1 for operational context;
- confusion matrix;
- top-2 accuracy as supporting information;
- expected calibration error or another declared calibration metric;
- Brier score where appropriate;
- abstention coverage;
- selective accuracy at several thresholds;
- p50 and p95 inference latency; and
- model artifact size.

### Required slices

- product class;
- month or quarter;
- narrative-length band;
- submission channel if it is used only for evaluation;
- common versus rare classes; and
- pre- and post-taxonomy-change periods if relevant.

### Fairness language

Do not describe these operational slices as demographic fairness testing.

The project may assess consistency and robustness across available operational groups. It cannot establish fairness across protected groups without suitable attributes, context, and stakeholder analysis.

### Error analysis

Manually review a stratified sample of:

- high-confidence correct cases;
- high-confidence errors;
- low-confidence correct cases;
- abstentions;
- rare-class errors;
- short narratives; and
- long truncated narratives.

Create a small error taxonomy, such as:

- multiple products in one narrative;
- vague language;
- taxonomy overlap;
- explicit but misleading keywords;
- insufficient context;
- label inconsistency; and
- model truncation.

---

## 12. Abstention and human oversight

### Why abstention matters

A model that always returns a category hides uncertainty. A controlled system should be able to say, “I do not have enough confidence to suggest a route.”

### Threshold selection

Choose the threshold using validation data and an explicit business trade-off.

Report a table like:

| Threshold | Coverage | Selective accuracy | Cases sent to review |
|---|---:|---:|---:|
| 0.50 | measured | measured | measured |
| 0.65 | measured | measured | measured |
| 0.80 | measured | measured | measured |

Do not populate results until they have been reproduced.

### Human-review policy

Manual review is required when:

- confidence is below the threshold;
- the input fails validation;
- the predicted class is outside the active taxonomy;
- the model or taxonomy version is unavailable;
- drift exceeds the declared warning threshold; or
- the reviewer identifies a multi-product or otherwise ambiguous case.

The public demo should display these rules in plain language.

---

## 13. Explainability

Use explanations appropriate to the deployed model.

For logistic regression:

- show influential n-grams with careful wording;
- explain that these are model features, not causal reasons; and
- guard against exposing sensitive fragments.

For a transformer:

- prefer global error analysis and example-based explanations;
- use local attribution only if it is stable and honestly described;
- do not present attention weights as definitive reasoning; and
- consider reason codes derived from a separate transparent mapping rather than claiming the model “thought” in human terms.

Every explanation must distinguish **model evidence** from **business justification**.

---

## 14. Responsible AI and governance pack

Align the documentation with the themes in Singapore's AI Verify framework:

- transparency;
- explainability;
- reproducibility;
- safety;
- security;
- robustness;
- fairness;
- data governance;
- accountability;
- human agency and oversight;
- societal and environmental considerations.

### Required documents

`docs/problem_statement.md`

- decision being supported;
- users;
- intended benefit;
- non-goals;
- harm analysis.

`docs/data_sheet.md`

- source;
- collection and publication context;
- filters;
- known limitations;
- retention;
- lineage.

`docs/model_card.md`

- model version;
- intended and prohibited uses;
- training window;
- evaluation window;
- metrics and slices;
- threshold;
- limitations;
- ethical considerations;
- maintenance plan.

`docs/risk_register.md`

At minimum, cover:

- misrouting;
- overconfidence;
- taxonomy drift;
- data poisoning;
- oversized or malformed inputs;
- model extraction and abuse;
- retention of submitted text;
- feedback manipulation;
- monitoring failure;
- dependency vulnerability;
- service outage; and
- misleading public claims.

`docs/human_oversight.md`

- review triggers;
- reviewer controls;
- escalation;
- override recording;
- responsibility boundaries.

`docs/change_management.md`

- model promotion checklist;
- required tests;
- approver role;
- rollback process;
- versioning convention.

`docs/security.md`

- threat model;
- secrets handling;
- CORS;
- validation;
- rate limiting;
- logging and redaction;
- dependency scanning;
- incident response.

---

## 15. Security and privacy controls

### Input controls

- enforce a minimum and maximum narrative length;
- reject binary or malformed input;
- normalize encoding;
- set request-body limits;
- time out expensive operations;
- return generic internal-error messages;
- log request IDs, not raw public-demo narratives; and
- do not treat HTML supplied in a narrative as markup.

### API controls

- explicit CORS allowlist;
- rate limiting;
- HTTPS in deployment;
- no model-path or stack-trace exposure;
- dependency vulnerability checks;
- model artifact checksum;
- readiness separate from liveness;
- stable API versioning.

### Frontend controls

- never place a secret API token in `VITE_*` variables because these are bundled into browser code;
- escape narrative content;
- avoid dangerously inserted HTML;
- show failures without leaking backend detail;
- disable repeated submission while a request is active; and
- provide a privacy notice beside the free-text field.

### Public-demo privacy

Prefer curated CFPB examples already published in the source dataset or synthetic examples. Warn visitors not to submit personal or confidential information. Do not retain arbitrary inputs.

---

## 16. Testing strategy

### Data tests

- schema contract;
- unique IDs;
- accepted target classes;
- date constraints;
- narrative null and length checks;
- split isolation;
- duplicate leakage;
- row-count reconciliation;
- source-schema change detection.

### Model tests

- feature pipeline can transform a fixed fixture;
- predicted probabilities sum appropriately;
- predicted labels belong to the active taxonomy;
- abstention works at boundary values;
- fixed model artifact reproduces expected fixture outputs within tolerance;
- missing model artifact fails readiness;
- evaluation rejects overlap between splits.

### API tests

- valid prediction;
- empty narrative;
- oversized narrative;
- invalid JSON;
- low-confidence abstention;
- model unavailable;
- model-info schema;
- request-ID propagation;
- CORS behaviour;
- no raw narrative in normal logs.

### Frontend tests

- keyboard navigation;
- visible focus;
- form label and error association;
- loading state;
- successful suggestion;
- abstention state;
- API unavailable state;
- correction interaction;
- chart text alternatives;
- small-screen layout;
- no information conveyed by colour alone.

### End-to-end smoke test

At minimum:

1. start database and API from a clean checkout;
2. load a small fixture dataset;
3. load the approved model artifact;
4. open the web app;
5. submit a demo narrative;
6. receive and display a suggestion or abstention;
7. record a reviewer action; and
8. verify the action in the database or mock store.

---

## 17. Vibe-coding operating method

Vibe coding is useful when AI accelerates implementation while you retain ownership of the problem, architecture, tests, and claims.

Use this loop for every issue:

```text
SPEC -> PLAN -> SMALL PATCH -> TEST -> EXPLAIN -> REVIEW -> COMMIT
```

### Rules for the AI coding assistant

Put these rules in `AGENTS.md` or the repository's equivalent instruction file:

1. Work on one bounded issue at a time.
2. Read the relevant specification and existing tests before editing.
3. State assumptions before implementation.
4. Do not change unrelated files.
5. Do not weaken or delete tests to make a build pass.
6. Do not fabricate metrics, screenshots, datasets, or operational claims.
7. Keep raw CFPB data and secrets out of Git.
8. Explain every new dependency and why the standard library or current stack is insufficient.
9. Add or update tests for every behaviour change.
10. Run the narrowest relevant tests first, then the full validation suite.
11. Report commands run and unresolved risks.
12. Stop and ask when a decision changes the data contract, model target, security boundary, or public claim.

### Your responsibilities while vibe coding

You must be able to explain:

- what every service does;
- where data enters and is stored;
- why the split prevents leakage;
- why each metric was chosen;
- how calibration and abstention work;
- what the API returns;
- where secrets live;
- what happens when the model fails; and
- which limitations remain.

If you cannot explain a generated component, do not merge it yet.

### Issue prompt template

```text
You are implementing issue <ID> for the Responsible AI Complaint Triage project.

Read:
- <relevant specification files>
- <relevant code files>
- <relevant tests>

Goal:
<one observable outcome>

Constraints:
- Do not modify unrelated files.
- Do not change the public API unless explicitly required.
- Do not add dependencies without explaining the need.
- Do not weaken tests.
- Do not fabricate data or metrics.

Before editing:
1. Summarise the current behaviour.
2. State assumptions and risks.
3. Propose a short implementation plan.

Then implement the smallest complete change, add tests, run them, and explain the result in plain language.
```

### Debug prompt template

```text
Diagnose this failure before changing code.

Expected behaviour:
<expected>

Observed behaviour:
<observed>

Reproduction command:
<command>

Error output:
<output>

Identify the most likely root cause, show the evidence, and propose the smallest fix. Do not edit tests unless the documented requirement is wrong.
```

### Learning checkpoint after each issue

Write three short notes:

1. What did the AI generate?
2. How did I verify that it was correct?
3. What can fail in production?

Store these in `docs/learning_log.md`. This becomes useful interview preparation.

---

## 18. Lovable prompting method

Do not ask Lovable to “build an AI dashboard” in one prompt. Give it the product contract and build page by page.

### Initial Lovable prompt

```text
Build a responsive React and TypeScript web application called “Responsible AI Complaint Triage”. It is a portfolio demonstration of a human-in-the-loop classifier for financial complaint narratives.

The application supports reviewers; it does not make final decisions. Its core states are suggestion, abstention, loading, invalid input, service unavailable, and reviewer correction.

Create these routes:
1. Overview
2. Review workspace
3. Model performance
4. Monitoring
5. Governance

Visual direction:
- calm regulatory operations interface;
- warm off-white or charcoal base;
- restrained sage or blue signal colour;
- highly readable typography;
- monospaced model metadata;
- minimal border radius;
- no gradients, glowing AI motifs, decorative robots, or fake real-time data;
- responsive from 320px upward;
- WCAG-conscious focus, labels, contrast, and non-colour status cues.

For now use typed fixture data behind an API service interface. Do not hard-code data directly into presentation components. Do not add authentication, payments, chat, or generative-AI features.

Before implementation, describe the component structure, data contracts, and page states.
```

### API integration prompt

```text
Replace the review workspace fixture service with the external FastAPI contract documented below. Use a single configurable API base URL. Add TypeScript types, request timeout handling, request-ID propagation, safe error messages, and explicit handling for suggestion and abstention responses.

Do not put secrets in browser environment variables. If authentication is required, stop and propose a server-side Edge Function proxy.

<paste the current OpenAPI contract or relevant schemas>
```

### Accessibility review prompt

```text
Audit the current application for keyboard operation, focus visibility, semantic headings, form labels, error association, screen-reader status announcements, chart alternatives, touch targets, contrast, reduced motion, and 320px layout. List issues before editing. Fix them without redesigning unrelated components, then explain how each fix can be manually verified.
```

### Lovable review rule

After each Lovable change:

- inspect the generated diff in GitHub;
- run the app locally;
- run lint, type checks, and tests;
- check browser console and network calls;
- verify mobile and keyboard behaviour;
- commit only after understanding the change.

---

## 19. Implementation roadmap

### Phase 0: project contract and repository foundation

Deliverables:

- README with problem and non-goals;
- architecture decision record;
- repository structure;
- dependency and environment setup;
- pre-commit or equivalent checks;
- CI skeleton;
- issue backlog;
- learning log.

Exit criteria:

- clean checkout can install dependencies;
- lint and an initial test run in CI;
- no raw data or secrets tracked.

### Phase 1: source profiling and ingestion

Deliverables:

- API/export investigation notebook;
- bounded extraction command;
- raw batch manifest;
- PostgreSQL schema and migration;
- raw-to-staging transformation;
- source and data-quality report.

Exit criteria:

- repeated ingestion is idempotent or explicitly append-only;
- row counts reconcile;
- source schema is captured;
- fixtures allow tests without downloading full data.

### Phase 2: analytical dataset and baseline

Deliverables:

- stable taxonomy decision;
- filtering report;
- temporal split;
- duplicate controls;
- majority baseline;
- TF-IDF logistic-regression baseline;
- reproducible evaluation command.

Exit criteria:

- test data remains untouched during tuning;
- split manifest is versioned;
- metrics are generated from code, not copied manually.

### Phase 3: deep-learning candidate

Deliverables:

- tokenizer and dataset pipeline;
- compact transformer training configuration;
- tracked experiments;
- calibration analysis;
- baseline-versus-transformer decision record.

Exit criteria:

- training is reproducible within documented limits;
- selected model follows the written utility rule;
- no unsupported claim that deep learning is superior.

### Phase 4: abstention and governance evaluation

Deliverables:

- confidence calibration;
- threshold analysis;
- error taxonomy;
- model card;
- data sheet;
- risk register;
- human-oversight policy.

Exit criteria:

- threshold is selected using validation data;
- final test results are frozen and reproducible;
- limitations are visible.

### Phase 5: FastAPI service

Deliverables:

- versioned prediction endpoint;
- health, readiness, and model-info endpoints;
- validation and error model;
- structured logging;
- rate-limit strategy;
- Docker image;
- OpenAPI artifact;
- API tests.

Exit criteria:

- service starts from a documented command;
- fixture prediction works;
- raw narratives do not appear in normal logs;
- all API tests pass.

### Phase 6: Lovable application

Deliverables:

- five defined routes;
- typed fixture service;
- real API integration;
- loading, abstention, error, and unavailable states;
- accessible charts and forms;
- GitHub synchronization;
- published preview.

Exit criteria:

- end-to-end demo works from the published UI;
- frontend contains no secret;
- keyboard and 320px smoke tests pass;
- governance page links to real documentation.

### Phase 7: monitoring and final portfolio packaging

Deliverables:

- drift report;
- model and data version display;
- screenshots;
- architecture diagram;
- short demo video if useful;
- portfolio MDX case study;
- resume bullets based only on measured evidence.

Exit criteria:

- public claims trace to generated artifacts;
- repository has a fast reviewer path;
- project can be demonstrated in under three minutes.

---

## 20. Suggested issue backlog

Create one GitHub issue per item:

1. Define intended use, non-goals, and target taxonomy.
2. Scaffold Python repository and CI.
3. Implement source metadata discovery.
4. Implement bounded CFPB extraction.
5. Create database migrations and raw ingestion.
6. Create staging transformations and data tests.
7. Profile taxonomy stability and select date window.
8. Implement temporal split and duplicate isolation.
9. Implement majority baseline.
10. Implement TF-IDF logistic-regression baseline.
11. Produce baseline evaluation report.
12. Implement transformer dataset and tokenizer pipeline.
13. Train compact transformer candidate.
14. Calibrate probabilities.
15. Evaluate abstention thresholds.
16. Complete error analysis.
17. Write model-selection decision record.
18. Implement model registry/artifact loading.
19. Implement FastAPI health and model-info endpoints.
20. Implement prediction endpoint.
21. Add validation, logging, and security controls.
22. Containerize the API.
23. Create Lovable frontend foundation.
24. Build review workspace with fixtures.
25. Build performance and monitoring views.
26. Build governance view.
27. Integrate the external API.
28. Complete accessibility and responsive review.
29. Complete governance documentation.
30. Capture final evidence and add portfolio case study.

---

## 21. Definition of done

The project is portfolio-ready only when all of the following are true.

### Reproducibility

- A clean checkout can install and run tests.
- The bounded data extraction is documented.
- Training and evaluation are commands, not notebook-only actions.
- Model and data versions appear in generated reports.

### Data science

- Majority, classical, and deep-learning candidates are compared.
- Temporal evaluation is used.
- Calibration and abstention are evaluated.
- Per-class and slice results are shown.
- Error analysis is documented.

### Engineering

- SQL-backed ingestion works.
- API contract is versioned and tested.
- Docker path works.
- CI passes.
- Logs and failures are handled deliberately.

### Responsible AI

- Intended and prohibited uses are explicit.
- Human review is operational, not decorative.
- Model card, data sheet, risk register, and security notes exist.
- Fairness limitations are stated accurately.
- No unsupported production or impact claim appears.

### Web application

- Lovable app uses the real API or a clearly marked fixture/demo mode.
- Suggestion and abstention are distinct.
- No secrets are shipped to the browser.
- UI is keyboard accessible and responsive.
- Metrics shown in the UI come from versioned evaluation artifacts.

### Communication

- README explains the project in under two minutes.
- A technical reader can reproduce the work.
- A recruiter can understand the decision and controls without reading code.
- The demo can be presented in under three minutes.

---

## 22. Interview demonstration script

### Minute 1: problem and boundary

“This system supports complaint routing. It does not determine truth, liability, or consumer outcomes. I used a temporal test set because the taxonomy and complaint language change over time.”

### Minute 2: model and decision

Show:

- baseline-versus-transformer comparison;
- calibration;
- the chosen threshold; and
- a suggestion followed by an abstention.

Explain why the operational model was selected, even if it is not the most complex model.

### Minute 3: production and governance

Show:

- API version;
- monitoring view;
- human correction;
- risk register; and
- model card limitation.

Finish with one thing you would validate with real stakeholders before production.

---

## 23. Resume bullet placeholders

Do not finalize these until results exist.

- Built an end-to-end financial complaint routing system using Python, PostgreSQL, FastAPI, and `<selected model>`, evaluated on a temporally held-out dataset of `<measured count>` narratives.
- Implemented calibrated abstention and human review, achieving `<measured selective accuracy>` at `<measured coverage>` while routing uncertain cases for manual assessment.
- Productionized ingestion, model evaluation, API testing, drift reporting, and governance documentation through Docker and CI, with `<measured test count or coverage if meaningful>` automated checks.

Replace placeholders only from reproduced artifacts.

---

## 24. Immediate first session

The first coding session should not train a model.

Complete these tasks:

1. Create the backend repository.
2. Add this specification or link to it.
3. Write `README.md` with intended use and non-goals.
4. Add `AGENTS.md` with the vibe-coding rules.
5. Add environment and dependency configuration.
6. Add one passing smoke test.
7. Add CI for lint and tests.
8. Create the first five GitHub issues.
9. Commit the clean foundation.
10. Only then begin source profiling.

This sequence makes the project easier to learn, review, and recover when AI-generated changes go wrong.
