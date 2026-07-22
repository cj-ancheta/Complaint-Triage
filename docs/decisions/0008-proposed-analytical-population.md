# ADR 0008: Versioned analytical population and exclusions

- Status: Accepted
- Date: 2026-07-22
- Decision owners: Charles Jr Ancheta and project maintainer
- Scope: row eligibility before temporal splitting and modelling

## Context

ADR 0007 fixed the source taxonomy and initial modelling window. Staging version
`1.0.0` now provides normalized, append-only outcomes, but staging acceptance is
only a source-quality result. CT-202 must define which staged rows are eligible
for the analytical dataset and report every exclusion without silently dropping
records.

This decision does not choose train/validation/test boundaries, cross-batch or
near-duplicate isolation, sampling, class weights, model features, or metrics.

## Decision

Create analytical-population version `1.0.0`. Evaluate every row from one
completed staging batch and record exactly one immutable outcome:

- `eligible`: no exclusion reason, an exact accepted target product, detected
  language `en`, and a positive narrative character count; or
- `excluded`: one or more reasons from the closed vocabulary below.

| Reason | Rule |
|---|---|
| `staging_quarantined` | The source row failed staging version `1.0.0`. Do not inspect its narrative for language. |
| `date_before_window` | `date_received < 2023-09-01`. |
| `date_at_or_after_window_end` | `date_received >= 2025-01-01`. |
| `product_outside_taxonomy` | `product_raw` is not one of the eleven exact ADR 0007 labels. |
| `language_not_english` | Lingua identifies a structurally eligible narrative as a non-English ISO 639-1 language. |
| `language_undetermined` | Lingua cannot identify a structurally eligible narrative. |

Date and product rules are evaluated before language identification. A row can
therefore have both a date and product reason, but language is not computed once
a structural reason already excludes it. This avoids unnecessary narrative
processing and means exclusion-reason counts are not expected to sum to the
number of excluded rows.

Do not impose a minimum narrative length. Staging already requires non-empty
text, and no measured evidence currently justifies discarding short complaints.
Record character length for aggregate profiling instead.

## Language detector

Use `lingua-language-detector` version 2.2.x in its offline, all-language,
high-accuracy mode. Record the exact installed version in every population run.
The existing standard library and data stack do not provide language
identification; this dependency is added only for the English-only population
rule already required by the project specification.

Lingua is a heuristic classifier, not language ground truth. Short, mixed, named-
entity-heavy, or code-switched complaints can be wrong. `language_undetermined`
is an exclusion rather than an implicit English default. Later error analysis
must sample language exclusions without publishing narratives.

## Persistence and privacy

Add append-only `analytical.population_runs` and
`analytical.population_outcomes` tables.

The run stores rule identities, exact window/taxonomy/detector versions, and
reconciled counts. Each outcome stores only staging lineage, eligibility, reason
codes, eligible target product, detected language code, and narrative character
count. It does not copy the narrative, complaint identifier, company, location,
or other source values into the analytical schema.

The CLI returns aggregate counts only. Narrative text is read locally for
language detection but never logged or included in the report.

## Versioning rule

Population version `1.0.0` means exactly this reason vocabulary, evaluation
order, taxonomy/window identity, and detector configuration. Any behavior change
must use a new population version and create new outcomes rather than updating
history.

Changes to taxonomy or window also require revisiting ADR 0007. Temporal split or
duplicate rules belong to CT-203 and must not be smuggled into this version.

## Consequences

Benefits:

- every staged row has an auditable disposition;
- source-quality, window, taxonomy, and language attrition are distinguishable;
- short but valid complaints are not removed arbitrarily;
- the report is reproducible and idempotent;
- narratives are not duplicated into the analytical schema;
- downstream splits can select eligible row lineage without redefining policy.

Costs and risks:

- the Lingua wheel is approximately 170 MB on the current Windows/Python 3.13
  environment;
- processing the eventual large extract will be CPU-intensive despite streaming
  database reads;
- language mistakes can systematically exclude valid complaints;
- per-batch reports assume the eventual bounded extract is represented by a
  declared ingestion batch;
- real attrition counts remain unavailable until a retention policy permits a
  real raw batch.

## Alternatives considered

### Treat every narrative as English

Rejected. It violates the declared population and silently adds multilingual
noise to a primarily English classifier.

### Use an ASCII or dictionary heuristic

Rejected. ASCII is not a language and English complaints can contain names,
loanwords, or Unicode punctuation. A hand-built word list would be less
reproducible and harder to validate.

### Add a minimum character or word count

Not proposed. No source measurement or operational requirement currently
justifies a threshold. Length remains a reported diagnostic.

### Resolve duplicates now

Rejected for CT-202. Cross-batch and near-duplicate decisions interact with
temporal splits and are explicitly scoped to CT-203.

## Approval

Charles explicitly approved the six exclusion reasons and evaluation order,
English-only eligibility using the recorded Lingua detector, no additional
minimum-length exclusion, and metadata-only analytical storage on 2026-07-22.

This approval does not select temporal split or duplicate-isolation rules. Those
remain separate CT-203 decisions.
