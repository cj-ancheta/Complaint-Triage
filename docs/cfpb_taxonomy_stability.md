# CFPB product-taxonomy stability profile

## Purpose and decision boundary

CT-201 profiles the official CFPB product labels over the August 2023 form
transition and proposes an initial modelling window. It does not ingest complaint
rows, read narratives, define the final analytical population, create a temporal
split, or train a model.

Charles approved the taxonomy and date window on 2026-07-22. The accepted
decision record is
[`docs/decisions/0007-proposed-taxonomy-window.md`](decisions/0007-proposed-taxonomy-window.md).

## Official evidence reviewed

| Evidence | What it establishes |
|---|---|
| [Consumer Complaint Database](https://www.consumerfinance.gov/data-research/consumer-complaints/) | The database updates generally daily; recent complaints and narratives can be incomplete; consumers select labels from the form available when they submit. |
| [April 2017 product and issue options](https://files.consumerfinance.gov/f/documents/201704_cfpb_Consumer_Complaint_Form_Product_and_Issue_Options.pdf) | The previous published taxonomy era began on 24 April 2017. |
| [August 2023 product and issue options](https://files.consumerfinance.gov/f/documents/cfpb_consumer_complaint_form_product_issue_options_August_2023_FINAL.pdf) | The current published form taxonomy became effective on 24 August 2023 and changed product, sub-product, issue, and sub-issue options. |
| [API release notes](https://cfpb.github.io/api/ccdb/release-notes.html) | The source contract continues to change; release 22 removed two export fields in June 2026, and release 13 records the April 2017 taxonomy restructure. |
| [Official API OpenAPI source](https://github.com/cfpb/ccdb5-api/blob/main/swagger-config.yaml) | `/trends` is the aggregate endpoint; its `overview` lens exposes product aggregations and monthly trend buckets without a complaint-hit result schema. |
| [2025 Consumer Response Annual Report](https://www.consumerfinance.gov/data-research/research-reports/2025-consumer-response-annual-report/) | Complaint intake changed materially in 2025: approximately 5.8 million of 6.6 million complaints received concerned credit or consumer reporting. This is evidence of an operational/distribution shift, not a reason to claim consumer harm. |

The annual report sometimes streamlines display labels and is not used as the
authoritative database taxonomy. Exact target strings come from the August 2023
form and the measured API buckets.

## Privacy-safe measurement method

The command uses one immutable HTTPS request:

```text
GET /data-research/consumer-complaints/search/api/v1/trends
  ?date_received_min=2023-07-01
  &date_received_max=2025-01-01
  &has_narrative=true
  &lens=overview
  &trend_depth=100
  &trend_interval=month
```

Why these boundaries:

- July and August 2023 reveal the transition from legacy labels.
- September 2023 is the first complete calendar month after the 24 August form
  change.
- The query ends at the January 2025 boundary so the proposed window can stop at
  December 2024 and avoid the documented 2025 intake shift.
- `has_narrative=true` measures the population relevant to a text classifier.
- `/trends` with `lens=overview` returns aggregates; row-returning parameters such
  as `size`, `frm`, `format`, and `search_term` are forbidden by code.

Additional safeguards:

- only the exact host, path, and query are accepted;
- redirects are disabled;
- the response is capped at 3 MB and must be JSON;
- any non-empty complaint `hits` list causes a controlled failure;
- incomplete product buckets and monthly/count mismatches cause a controlled
  failure;
- response bodies are neither logged nor persisted; and
- tests use a hand-authored aggregate fixture, never a live complaint response.

Run it with:

```powershell
.\.venv\Scripts\python.exe -m complaint_triage profile-taxonomy
```

The command prints aggregate labels and counts. For a compact review, redirect
the parsed Python object to a summary in memory rather than storing the upstream
response. Do not commit live response bodies.

## Measured result

Measurement time: **2026-07-22T08:22:32.687351+00:00**

The official endpoint returned HTTP 200 and 303,466 bytes in the observed run.
The request-window product total was 1,068,515 and reconciled exactly to the
product buckets and their monthly series. The candidate window contains
**979,996** aggregate records across all expected 16 months.

The trends response included a January 2025 boundary bucket even though the
documented maximum-date contract is exclusive. The profiler does not assume the
bucket is in scope: candidate counts include only month keys before `2025-01-01`.
The later row-level extraction must independently enforce and reconcile the exact
date predicate.

| Exact product label | Candidate count | Share |
|---|---:|---:|
| Checking or savings account | 38,179 | 3.90% |
| Credit card | 47,568 | 4.85% |
| Credit reporting or other personal consumer reports | 747,603 | 76.29% |
| Debt collection | 82,072 | 8.37% |
| Debt or credit management | 1,838 | 0.19% |
| Money transfer, virtual currency, or money service | 13,210 | 1.35% |
| Mortgage | 16,228 | 1.66% |
| Payday loan, title loan, personal loan, or advance loan | 6,636 | 0.68% |
| Prepaid card | 5,002 | 0.51% |
| Student loan | 11,880 | 1.21% |
| Vehicle loan or lease | 9,780 | 1.00% |
| **Total** | **979,996** | **100.00%** |

All eleven current labels appeared. No known legacy label and no unexpected label
appeared in September 2023 through December 2024. The aggregate supports taxonomy
stability over that interval, but it does not prove that every class will have
enough usable English, deduplicated rows after CT-202 and CT-203.

The overview response also contains a `dateRangeBuckets` series used by the CFPB
interface as broader date context. It did not equal the filtered product total
and is recorded as non-decisional context rather than forced into a false
reconciliation. Candidate completeness and counts use the filtered per-product
monthly series, all of which reconciled.

## Taxonomy transition observed

The July/August transition contains legacy labels that do not appear in the
candidate window:

- `Credit card or prepaid card` became separate `Credit card` and `Prepaid card`
  products;
- `Credit reporting, credit repair services, or other personal consumer reports`
  became `Credit reporting or other personal consumer reports`, while credit
  repair and debt settlement moved under the new `Debt or credit management`
  product; and
- `Payday loan, title loan, or personal loan` became `Payday loan, title loan,
  personal loan, or advance loan`.

August is a mixed transition month because the new form became effective on 24
August. Starting on 1 September avoids pretending that a partial month belongs
cleanly to either version.

## Interpretation and limitations

- The class distribution is severely imbalanced. A majority classifier could
  appear accurate while being operationally useless, so macro metrics and
  per-class results will be mandatory.
- Aggregate counts are upstream, mutable observations made on one date. The
  eventual raw extract must record its own timestamp, checksum, row counts, and
  class distribution.
- `has_narrative=true` does not establish English language, minimum text quality,
  uniqueness, or modelling eligibility.
- Complaint volume is not a statistical estimate of consumer experience and must
  not be used to rank companies or infer harm without exposure data.
- The absence of a legacy label in aggregate buckets is evidence for this window,
  not proof that the source can never backfill or revise a record.
- The smallest class has 1,838 aggregate records before later exclusions. CT-202
  must report attrition rather than silently create an `Other` class or drop it.

## Accepted recommendation

Adopt taxonomy version `cfpb-product-2023-08-24` with identity mapping to the 11
exact labels in the table, and use the modelling window:

```text
date_received >= 2023-09-01
date_received <  2025-01-01
has_narrative = true
```

Do not map legacy categories into the current taxonomy and do not create an
`Other` category. CT-202 should apply and report population-quality exclusions
against these 11 eligible labels. If evidence later supports excluding a class,
that would change the approved target and must return through the decision gate.

Alternatives not recommended:

1. Include 2025 for recency. This introduces a documented intake/distribution
   shift before the baseline is understood.
2. Include pre-September 2023 data and map legacy labels. This adds ambiguous
   semantics, including a combined card/prepaid label that cannot be split
   truthfully from its top-level label.
3. Merge rare products into `Other`. This hides distinct routing destinations
   and makes errors harder to interpret.

## Recorded decision and next gate

Charles approved both:

1. the exact 11-label `cfpb-product-2023-08-24` identity taxonomy; and
2. the inclusive/exclusive window `2023-09-01 <= date_received < 2025-01-01`.

CT-201 is complete. CT-202 may now define and measure analytical-population
exclusions against the accepted taxonomy and window. Temporal
train/validation/test boundaries remain a separate CT-203 phase gate.
