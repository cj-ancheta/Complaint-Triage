# CFPB Source Inventory

- Issue: CT-101
- Status: review
- Research date: 2026-07-21
- Scope: official contract and source-risk investigation only
- Data downloaded: none

## Outcome

The CFPB Consumer Complaint Database is a viable source for the proposed routing study, but it must be treated as a mutable, versioned publication rather than a static benchmark.

The official OpenAPI contract exposes the narrative and product fields required for the initial classification question. It also exposes metadata that would create target leakage, post-decision leakage, shortcut learning, or unnecessary privacy risk if used as model features.

No modelling population, date window, target taxonomy, or split has been approved in CT-101.

## Official sources consulted

| Source | Version or freshness observed | Purpose |
|---|---|---|
| [Consumer Complaint Database](https://www.consumerfinance.gov/data-research/consumer-complaints/) | Page last modified 2025-10-20; accessed 2026-07-21 | Publication process, limitations, downloads, taxonomy-change references |
| [API documentation](https://cfpb.github.io/api/ccdb/api.html) | Accessed 2026-07-21 | Official API entry point |
| [OpenAPI definition](https://github.com/cfpb/ccdb5-api/blob/main/swagger-config.yaml) | OpenAPI 3.0; API version 1.0.0; `main` commit `b4f292524c40e4fd154b9350bf8335ade3e0b5e9` observed 2026-07-21 | Endpoints, parameters, response schema, runtime field names |
| [Field reference](https://cfpb.github.io/api/ccdb/fields.html) | Accessed 2026-07-21 | Human-readable field meaning and type notes |
| [Release notes](https://cfpb.github.io/api/ccdb/release-notes.html) | Release 22, June 2026 | Recent schema/export changes and historical taxonomy changes |
| [How CFPB shares complaint data](https://www.consumerfinance.gov/complaint/data-use/) | Page last modified 2025-09-12; accessed 2026-07-21 | Publication, narrative consent/scrubbing, ZIP masking, field context |

The OpenAPI commit is recorded to make this inventory reproducible. It is not an assertion that the deployed API always matches that commit.

## Publication context

The following constraints come from the official CFPB descriptions and must remain visible throughout the project:

- Only complaints sent to companies for response are eligible for publication.
- Complaints are generally published after a company responds and confirms a commercial relationship, or after 15 days, whichever comes first.
- Narratives are published only when consumers opt in and after CFPB takes steps to remove personal information.
- Consumers may later opt out of narrative publication.
- Recent records may not yet have all eligible narratives because narrative processing takes time.
- The database is not a statistical sample and is not representative of all consumer experiences.
- Complaint volume cannot be interpreted as company harm without exposure, market-share, population, and reporting-behaviour context.
- Consumer narratives describe the consumer's experience and are not independently verified by the CFPB.

## API surface

The OpenAPI definition declares this server:

```text
https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/
```

Relevant endpoints:

| Endpoint | Purpose | CT-101 relevance |
|---|---|---|
| `GET /` | Search complaints | Candidate bounded profiling and later ingestion source |
| `GET /{complaintId}` | Retrieve one complaint | Possible debugging only; not the preferred bulk path |
| `GET /trends` | Aggregated complaint trends | Possible taxonomy and distribution research |
| `GET /geo/states` | State aggregations | Not required for the MVP |
| `GET /_suggest*` | UI suggestion helpers | Not required for the MVP |

The search response contains:

- `_meta` with data freshness, update, license, total-record, and pagination information;
- `hits.total` with matching-count metadata;
- `hits.hits[*]._source` with complaint fields; and
- optional aggregations unless `no_aggs=true` is requested.

Useful `_meta` fields declared in the contract:

- `break_points`;
- `has_data_issue`;
- `is_data_stale`;
- `is_narrative_stale`;
- `last_indexed`;
- `last_updated`;
- `license`; and
- `total_record_count`.

These should be captured in future batch manifests. A successful HTTP response alone is not enough if the source reports stale data or a load issue.

## Runtime field inventory

The field names below come from the current OpenAPI `Complaint` schema. Nullability and actual deployed behaviour still require a bounded live check.

| API field | Declared type | Meaning | Proposed role | Feature status |
|---|---|---|---|---|
| `complaint_id` | integer | Unique complaint identifier | Deduplication and lineage | Never a model feature |
| `date_received` | date string | Date CFPB received the complaint | Temporal split and monitoring | Metadata only |
| `product` | string | Product selected by the consumer | Candidate target | Target candidate; approval required |
| `sub_product` | string | Dependent sub-product selection | Taxonomy analysis | Not an input; target decision deferred |
| `issue` | string | Issue selected within product | Taxonomy analysis | Excluded because it encodes the target hierarchy |
| `sub_issue` | string | Sub-issue dependent on product and issue | Taxonomy analysis | Excluded because it encodes the target hierarchy |
| `complaint_what_happened` | string | Published consumer narrative | Primary text input | Candidate model input |
| `has_narrative` | boolean | Narrative-availability indicator | Source filter and quality check | Filter only |
| `company` | string | Company identified in the complaint | Audit and slice context | Excluded to avoid company shortcuts |
| `company_public_response` | string | Optional public company response | Post-complaint context | Excluded as post-routing leakage |
| `company_response` | string | Company's response category | Outcome context | Excluded as post-routing leakage |
| `date_sent_to_company` | string | Date sent to company | Process metadata | Excluded as post-routing information |
| `timely` | string | Whether company response was timely | Outcome metadata | Excluded as post-routing leakage |
| `submitted_via` | string | Submission channel | Operational evaluation slice | Excluded from MVP model input |
| `state` | string | Consumer mailing state | Operational evaluation context | Excluded from MVP model input |
| `zip_code` | string | Published full, partial, or blank ZIP | Geographic metadata with masking | Excluded for privacy and proxy risk |
| `tags` | string | Includes reported Older American and Servicemember tags | Governance context | Excluded from model input; potentially sensitive proxy |

### Label differences

The website and CSV use human-facing labels such as “Consumer complaint narrative” and “Timely response?”. The JSON API uses stable-looking machine keys such as `complaint_what_happened` and `timely`.

The ingestion contract must record both the source format and its field mapping. Code must not assume CSV and JSON use identical column names.

## Search parameters relevant to a bounded request

| Parameter | Contract behaviour | Important constraint |
|---|---|---|
| `size` | 1 to 100, default 10 | Use a small value during source profiling |
| `frm` | Starting index for non-export requests | OpenAPI declares minimum 1 but default 0; verify deployed behaviour |
| `date_received_min` | Inclusive lower receipt-date bound | Use an explicit fixed date |
| `date_received_max` | Exclusive upper receipt-date bound | One-day range requires the following date as maximum |
| `has_narrative` | Filters narrative availability | Documentation describes yes/no strings but has no enum; verify accepted representation |
| `no_aggs` | Omits aggregations when true | Use true for small profiling responses |
| `no_highlight` | Omits search highlighting when true | Use true unless highlighting is being studied |
| `sort` | Includes `created_date_desc/asc` and relevance values | “created date” is not a declared complaint field; do not treat it as `date_received` without verification |
| `product` | Product or `Product•Sub-product` | Taxonomy labels and delimiter require careful encoding |
| `issue` | Issue or `Issue•Sub-issue` | Dependent taxonomy; not a model feature |
| `search_after` | Deep-pagination cursor derived from `_meta.break_points` | Prefer documented cursor pagination over large offsets |
| `format` | `json` or `csv` export | If supplied, the contract says `frm` and `size` are ignored |

### Critical export warning

Do not add `format=json` or `format=csv` to a profiling request that relies on `size` for boundedness. The official OpenAPI description states that specifying an export format causes `frm` and `size` to be ignored.

The profiling path must omit `format` and rely on the ordinary JSON search response.

## Recent and historical schema changes

### June 2026 release

Release 22 removed these fields from CSV and JSON exports so exports mirror the current user interface:

- `Consumer disputed`;
- `Consumer consent provided`.

Neither field appears in the current OpenAPI `Complaint` schema. The older “How CFPB shares complaint data” page still describes both, so the official pages are not perfectly synchronized.

The project must prefer the versioned OpenAPI contract plus a live source check, while documenting disagreements between official sources.

### Taxonomy changes

The CFPB states that it preserves the product, sub-product, issue, and sub-issue selections that were available when each complaint was submitted.

Two major published taxonomy eras are directly relevant:

- April 2017 through August 2023;
- August 2023 to the present.

This means a broad historical extract can contain label and hierarchy drift even when the text problem appears unchanged. The post-August-2023 taxonomy is a candidate for the first modelling window, but selecting it is a CT-201 phase-gated decision, not a CT-101 conclusion.

## Source and modelling risks

| Risk | Why it matters | Planned control |
|---|---|---|
| Non-representative publication | Evaluation cannot generalize to all consumers or all complaints | Constrain claims and retain source limitations in model card |
| Consumer-selected labels | `product` is routing-form ground truth, not independently adjudicated truth | Describe the target as reproducing published routing categories |
| Taxonomy drift | Historical categories and wording differ | Profile labels by time before selecting a modelling window |
| Narrative opt-in and removal | Narrative availability is selective and may change retrospectively | Version snapshots and report narrative coverage |
| Recent-data lag | Latest complaints and narratives may be incomplete | Record source freshness metadata and apply a maturity buffer |
| Residual privacy risk | CFPB scrubs personal information, but free text remains sensitive | Keep raw narratives out of Git and suppress them in logs/reports |
| Target leakage | Issue/sub-issue depend on product | Use narrative as the primary model input; exclude dependent labels |
| Post-decision leakage | Company response and timeliness occur after routing | Exclude from features |
| Shortcut learning | Company or location can dominate product prediction | Exclude company, state, ZIP, and tags from MVP input |
| Proxy and sensitivity risk | Tags can identify older Americans or servicemembers; geography can proxy groups | Exclude from model input and avoid unsupported fairness claims |
| Class imbalance | Product categories may differ greatly in volume | Use macro metrics, per-class results, and threshold analysis |
| Mutable daily source | Re-running the same dates can produce different rows | Store extraction timestamp, checksum, field inventory, and batch manifest |
| API/export divergence | Human labels and JSON keys differ; release notes show removals | Version source-format mappings and test contracts |
| API contract inconsistency | `frm` minimum/default conflict and loose enums exist | Verify parameters with bounded live calls before implementation |
| Access availability | The API returned CDN 403 from the current execution environment | Test from the user's normal network; define an official-export fallback later |
| Jurisdictional context | CFPB data represents a US regulator, while target roles are in Singapore | Frame project as transferable regulated-AI engineering, not Singapore complaint operations |

## Live-access observation

Two bounded attempts were made on 2026-07-21 using:

```text
GET /?size=1&no_aggs=true&no_highlight=true&has_narrative=true&sort=created_date_desc
```

Both PowerShell and `curl` received HTTP 403 from the CFPB CDN in this execution environment. No response payload or complaint narrative was retrieved.

This issue does not attempt to bypass the CDN restriction. CT-102 should test a bounded call from the user's normal browser/network and preserve a safe fallback design.

## Proposed bounded CT-102 request

CT-102 should validate the deployed contract with a request shaped like:

```text
GET https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/
    ?date_received_min=<fixed-date>
    &date_received_max=<following-date>
    &has_narrative=<verified-value>
    &no_aggs=true
    &no_highlight=true
    &size=5
    &sort=created_date_desc
```

Requirements for the check:

1. Omit `format` so `size` remains effective.
2. Use fixed historical dates, not “today”, for reproducibility.
3. Start with five or fewer records.
4. Print only response metadata, field names, null/type observations, and counts.
5. Suppress narrative and company values from console output.
6. Record status code, content type, request timestamp, source freshness flags, and observed field set.
7. Compare observed fields with this inventory.
8. Do not save raw records in the repository.
9. Stop if the API returns unexpected export volume or a different schema.

The exact date and `has_narrative` representation should be selected during CT-102 after a browser-level check. CT-102 remains profiling only and must not add PostgreSQL or modelling.

## CT-101 acceptance check

- [x] Current official field inventory documented.
- [x] API endpoints and bounded-search parameters documented.
- [x] June 2026 schema change recorded.
- [x] Taxonomy eras identified without selecting a target window.
- [x] Feature leakage and privacy risks classified.
- [x] Live access was attempted without downloading a dataset.
- [x] CDN failure was documented rather than bypassed.
- [x] Bounded CT-102 request and safeguards proposed.
- [x] No raw complaint or narrative was written to Git.

