# ADR 0006: Versioned staging outcomes with explicit quarantine reasons

- Status: Accepted
- Date: 2026-07-22
- Decision owners: Charles Jr Ancheta and project maintainer
- Scope: deterministic raw-to-staging source-quality transformations

## Context

CT-106 preserves source-aligned payloads in append-only raw tables. Those JSONB
rows are intentionally unsuitable as a direct modelling input: dates and nulls
are not typed, required routing fields can drift, identifiers can conflict, and
bad rows need an observable disposition.

The next step must not silently drop malformed rows. It must also avoid crossing
the Phase 2 gates for the modelling population, product taxonomy, date window,
temporal split, or duplicate isolation across splits.

## Decision

Create a dedicated `staging` schema with two append-only tables:

- `staging.transformation_batches` records one raw batch, transformation version,
  and reconciled input, accepted, quarantined, and output counts.
- `staging.complaint_outcomes` records exactly one outcome for every raw row and
  transformation version.

The primary keys include `transformation_version`. A future behavior change must
use a new version and produce new outcomes rather than overwrite history.

Use one outcome table rather than separate accepted and quarantine tables. This
makes the invariant visible and enforceable:

```text
input count = output count = accepted count + quarantined count
```

Every output has status `accepted` or `quarantined`. Accepted rows must have an
identifier, typed date, normalized narrative and narrative checksum, and raw
product label. Quarantined rows must have one or more reason codes. PostgreSQL
checks enforce these relationships, while triggers reject updates and deletes.

## Transformation version 1.0.0

Version 1.0.0 performs only reversible source-quality normalization:

- strings are normalized to Unicode NFC;
- CRLF and CR become LF;
- surrounding whitespace is removed;
- empty strings become null;
- `date_received` must be exact ISO `YYYY-MM-DD` and becomes a PostgreSQL date;
- string or integer complaint IDs become trimmed strings;
- normalized narratives receive a SHA-256;
- `product`, `sub_product`, `issue`, `sub_issue`, and `submitted_via` retain their
  source meaning and are named with a `_raw` suffix;
- the raw source-record checksum is recomputed from canonical JSON; and
- all occurrences of a complaint ID duplicated within the same batch are
  quarantined.

No case folding, stemming, language filtering, label merging, canonical product
mapping, date-window filter, or modelling inclusion rule is applied.

## Closed quarantine reason vocabulary

| Reason | Meaning |
|---|---|
| `source_record_checksum_mismatch` | Stored payload no longer matches its raw lineage checksum. |
| `complaint_id_missing_or_invalid` | Source complaint ID is absent, empty, Boolean, or unsupported. |
| `raw_complaint_id_mismatch` | Payload complaint ID disagrees with the raw identity column. |
| `date_received_invalid` | Receipt date is absent or not exact ISO `YYYY-MM-DD`. |
| `narrative_missing_or_invalid` | Narrative is absent, non-text, or empty after trimming. |
| `product_missing_or_invalid` | Raw product is absent, non-text, or empty after trimming. |
| `has_narrative_not_true` | Source narrative flag is not Boolean `true`. |
| `duplicate_complaint_id_within_batch` | The normalized ID occurs more than once in the raw batch. |

Reason order is deterministic and code-owned. CLI output reports only aggregate
counts, not source values or narratives.

## Important boundaries

An `accepted` staging outcome means only that this source-quality contract passed.
It does not mean that the row:

- belongs to the final modelling population;
- uses an approved product taxonomy;
- falls inside an approved modelling window;
- is English;
- is free from cross-batch or near-duplicate leakage; or
- may be used for training or evaluation.

Within-batch duplicates are all quarantined because selecting a winner by row
order would be arbitrary. Cross-batch and near-duplicate isolation require a
dataset-wide view and remain deferred to the analytical/split issues.

## Consequences

Benefits:

- no raw row disappears silently;
- quarantine is queryable, versioned, and reconciled;
- rerunning the same version is idempotent;
- normalized fields are typed without modifying raw history;
- later analytical rules can distinguish source quality from modelling policy;
- the implementation needs no new dependency.

Costs and limits:

- normalized narratives are duplicated in the local database;
- a quarantined row may still contain other valid normalized fields;
- the reason vocabulary requires a new transformation version when semantics
  change;
- checksum verification assumes the canonical JSON representation defined by the
  raw loader;
- append-only controls can be altered by the database owner;
- dataset-wide duplicates and taxonomy drift are not solved here.

## Alternatives considered

### Separate accepted and quarantine tables

Rejected. Proving that every input appears in exactly one of two tables requires
more coordination and makes reconciliation queries easier to get wrong.

### Drop invalid rows and report only counts

Rejected. Counts alone do not support root-cause review, deterministic reruns, or
evidence that the same source row receives the same disposition.

### Canonicalize CFPB product labels now

Rejected. That would select a taxonomy strategy before the required taxonomy
stability analysis and explicit approval.

### Deduplicate across all batches now

Rejected. Append-only per-batch outcomes cannot safely select a global winner
without an approved analytical population and temporal ordering rule.

## Acceptance evidence

Accept this ADR when review confirms that:

- pure tests cover normalization and every quarantine reason;
- a disposable PostgreSQL test proves forced rollback, clean acceptance,
  quarantine storage, count reconciliation, replay, and mutation rejection;
- the migration preserves both raw and versioned staging lineage;
- CLI output is aggregate-only and safe; and
- documentation clearly separates staging acceptance from modelling inclusion.
