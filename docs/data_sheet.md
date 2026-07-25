# CFPB Complaint Narrative Dataset Sheet

- Dataset card version: `1.0.0`
- Research run: `cfpb-run-20260722T130728Z-2b7815d4c850`
- Population version: `1.0.0`
- Split version: `1.0.0`
- Taxonomy: `cfpb-product-2023-08-24`
- Governance status: local retained research data; not approved for public
  redistribution

## Source and collection context

The source is the United States Consumer Financial Protection Bureau's public
[Consumer Complaint Database](https://www.consumerfinance.gov/data-research/consumer-complaints/).
The project used the official public download interface and API contract to
retrieve sixteen whole-month shards covering `2023-09-01 <= date_received <
2025-01-01`. The bounded run was acquired on 2026-07-22 and reconciled through
source, raw, staging, and analytical layers.

The database contains complaints submitted to the CFPB and sent to companies
for response. Publication is not a random sample of consumers, financial
products, harm, or company behavior. The CFPB's publication process can change,
recent records may be incomplete, and complaint volume can be affected by
submission channels, repeat submissions, company practices, public awareness,
and taxonomy changes. A published narrative may still describe sensitive
personal or financial circumstances even after CFPB scrubbing.

The CFPB did not create this dataset for training an automated complaint router,
and its publication does not establish the truth or legal merit of a complaint.

## Dataset purpose and non-purpose

The dataset supports a portfolio research question: can narrative text help a
human reviewer identify one of eleven current CFPB product categories while
keeping uncertainty and class imbalance visible?

It must not be used to infer truth, liability, compensation, vulnerability,
fraud, creditworthiness, legal outcome, or an appropriate company response. It
is not approved for automated routing, consumer-facing decisions, or evaluation
of individual companies or demographic groups.

## Raw and analytical populations

The retained run reconciles 979,995 staged records. All passed staging; the
analytical population retained 979,194 English-language records and excluded
801 records identified as non-English by Lingua `2.2.x`. No minimum narrative
length was applied. Eligible narrative length ranged from 10 to 32,962 Unicode
code points, with a mean of 983.736.

The language detector is heuristic. It can misclassify short, code-switched,
named-entity-heavy, or multilingual text. `language_undetermined` and
non-English outcomes are exclusions, not evidence that the complaints are
invalid.

Only the complaint narrative is a model feature. Product is the target. Company,
ZIP code, state, tags, complaint outcome, response, timeliness, dispute status,
and other source metadata are excluded as unnecessary, privacy-sensitive, or
potentially leaky features.

## Target taxonomy

The eleven exact targets are:

1. Checking or savings account
2. Credit card
3. Credit reporting or other personal consumer reports
4. Debt collection
5. Debt or credit management
6. Money transfer, virtual currency, or money service
7. Mortgage
8. Payday loan, title loan, personal loan, or advance loan
9. Prepaid card
10. Student loan
11. Vehicle loan or lease

The mapping is identity-only. Legacy labels are not mapped into the current
taxonomy, valid classes are not merged into `Other`, and the vocabulary must not
change without a new taxonomy version and explicit approval.

## Duplicate isolation and temporal split

Narratives are normalized with Unicode NFC, Unicode case folding, and collapsed
whitespace before SHA-256 fingerprinting. Groups with conflicting labels are
fully excluded. For a same-label group, the earliest record is retained and
later duplicates are excluded. This yielded 561,342 canonical rows and 417,852
duplicate-related exclusions:

| Partition | Inclusive start | Exclusive end | Records | Use |
|---|---|---|---:|---|
| Train | 2023-09-01 | 2024-09-01 | 394,564 | Model fitting |
| Validation | 2024-09-01 | 2024-11-01 | 80,992 | Epoch/model/calibration/threshold decisions |
| Test | 2024-11-01 | 2025-01-01 | 85,786 | Frozen and untouched |

Exact normalized duplicates do not cross included partitions. The method does
not detect paraphrases, templated near-duplicates, or semantically equivalent
text. More aggressive matching could also merge materially different cases and
was not introduced without evidence.

## Distribution and representation

The eligible source population is severely imbalanced: credit reporting
accounts for most records, while Debt or credit management is rare. After
deduplication, training support ranges from 1,173 to 248,062 records per class;
validation support ranges from 227 to 54,012. This imbalance drives metric
variance and contributed to the failure of the class-aware abstention policy.

Operational month, narrative-length, and class-frequency slices are not
demographic fairness evidence. Protected attributes are neither collected for
modelling nor evaluated. The project therefore makes no equal-performance or
demographic fairness claim.

## Transformations and lineage

The governed path is:

```text
16 monthly CFPB shards
  -> content-addressed raw manifests
  -> append-only raw tables
  -> staging transformation 1.1.0
  -> analytical population 1.0.0
  -> duplicate-isolated temporal split 1.0.0
  -> narrative-only model pipelines
  -> aggregate evaluation reports
```

The population report SHA-256 is
`36bae4066aae0cba826b46f24ae2158c9432da231e95bf7eb0a2a70ca25c3b88`.
The split manifest SHA-256 is
`8685eefd10d764d813dee2891e930323c22592850d537b0571956f390afe554b`.
The complete checked evidence list is in
[`governance_evidence.json`](governance_evidence.json).

## Retention and deletion

ADR 0009 policy `cfpb-local-120d-v1` permits row-level text only on Charles's
local development machine and loopback-only project PostgreSQL volume. Covered
data must not enter Git, GitHub releases, CI artifacts, cloud storage, shared
drives, backups, prompts, screenshots, or the public web application.

The absolute deletion deadline is 2026-11-19 end of day, Asia/Singapore. Cleanup
must remove ignored raw/intermediate artifacts, the PostgreSQL volume, and any
governed text-bearing derivative, then retain only a commit-safe deletion record
and aggregate evidence. There is no authorized backup or recovery copy.

## Known limitations

- Public CFPB complaints are not representative of all consumers or complaints.
- Labels reflect the source taxonomy, not independently adjudicated ground
  truth.
- English filtering can be wrong and excludes multilingual use.
- Exact normalized fingerprinting does not remove semantic near-duplicates.
- The 2023–2024 window does not establish behavior under later intake or
  taxonomy shifts.
- Narrative truncation at 384 model tokens can omit relevant context.
- Validation was reused for several research decisions, making its results
  optimistic tuning evidence.
- The frozen test has not been accessed, so no final generalization estimate
  exists.
- Row-level reproduction will end after required data deletion.

## Stewardship and contact boundary

The project maintainer is responsible for retention, evidence integrity,
cleanup, taxonomy changes, and approval gates. Any new data source, target,
window, feature, retention behavior, or public use requires a reviewed decision
before data access or implementation.
