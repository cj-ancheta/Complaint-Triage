# ADR 0007: Current-form product taxonomy and pre-2025 window

- Status: Accepted
- Date: 2026-07-22
- Decision owners: Charles Jr Ancheta and project maintainer
- Scope: initial target-product vocabulary and modelling date window

## Context

The CFPB complaint form changed on 24 August 2023. A privacy-safe aggregate
profile found legacy and current product labels together during the transition,
but only the eleven current labels from September 2023 onward. The 2025 CFPB
annual report also documents a large complaint-intake shift concentrated in
credit and consumer reporting.

The complete evidence, measured counts, source links, and limitations are in
[`docs/cfpb_taxonomy_stability.md`](../cfpb_taxonomy_stability.md).

## Decision

Use taxonomy version `cfpb-product-2023-08-24` and retain these exact source
labels as distinct eligible model targets:

1. `Checking or savings account`
2. `Credit card`
3. `Credit reporting or other personal consumer reports`
4. `Debt collection`
5. `Debt or credit management`
6. `Money transfer, virtual currency, or money service`
7. `Mortgage`
8. `Payday loan, title loan, personal loan, or advance loan`
9. `Prepaid card`
10. `Student loan`
11. `Vehicle loan or lease`

The initial mapping is identity-only. Do not map legacy labels into current
labels, merge targets, or create an `Other` class.

Use this initial modelling window:

```text
date_received >= 2023-09-01
date_received <  2025-01-01
has_narrative = true
```

The end boundary is exclusive. This decision does not yet choose language,
quality, duplicate, or split rules.

## Why this option was accepted

- September is the first full month after the current form became effective.
- All eleven labels appear when the candidate window is considered as a whole;
  no legacy or unexpected label appeared.
- The 16-month interval has 979,996 narrative-bearing aggregate records before
  analytical exclusions.
- Ending before 2025 avoids mixing the first baseline with the documented 2025
  credit-reporting intake shock.
- Identity mapping keeps target meaning explainable and auditable.

## Consequences

Benefits:

- one official, internally consistent taxonomy era;
- no untruthful split of the old combined card/prepaid category;
- clear versioning for model outputs and evaluation artifacts;
- a mature historical window unaffected by recent-publication incompleteness;
- class-specific evaluation remains possible.

Costs and risks:

- credit reporting represents 76.29% of the pre-exclusion aggregate population;
- `Debt or credit management` has only 1,838 aggregate records before exclusions;
- the window deliberately trades recency for a cleaner first baseline;
- later filtering may show that one or more classes lack adequate train,
  validation, or test support.

CT-202 must report attrition and class support. Any later class exclusion, merge,
or remapping changes this decision and requires explicit approval. CT-203 must
separately propose temporal split boundaries and duplicate-isolation behavior.

## Alternatives considered

### Add 2025

Not proposed for the first baseline. The annual report shows an exceptional
credit-reporting concentration and changed submission behavior, which should be
treated as a future temporal stress period rather than silently mixed into
training.

### Map older taxonomy eras

Not proposed. Several changes are not one-to-one, so a top-level mapping would
invent information or collapse routing destinations.

### Merge rare labels into `Other`

Not proposed. This weakens business meaning and can conceal poor performance on
low-volume but valid routes.

## Approval

Charles explicitly approved the eleven-label identity taxonomy and the exact
inclusive/exclusive date boundaries on 2026-07-22. This approval does not extend
to analytical exclusions, temporal split boundaries, or duplicate-isolation
rules, which remain separate decisions.
