# ADR 0010: Temporal split and normalized duplicate isolation

- Status: Accepted
- Date: 2026-07-23
- Decision owners: Charles Jr Ancheta and project maintainer
- Scope: analytical split version `1.0.0`

## Context

ADR 0007 fixes the modelling window and eleven-label taxonomy. ADR 0008 yields
979,194 eligible English narratives. CT-203 must create future-facing train,
validation, and untouched test partitions without allowing repeated narrative
text to cross them.

Aggregate-only discovery found substantial duplication. Exact narrative hashes
formed 62,286 duplicate groups and 3,054 groups crossed the candidate time
boundaries. A conservative case-and-whitespace normalization found 69,118
duplicate groups; 1,025 groups contained conflicting product labels. A naive
row-wise temporal assignment would therefore leak repeated text and preserve
contradictory supervision.

## Decision

Use split version `1.0.0` with whole-month boundaries:

| Split | Inclusive start | Exclusive end |
|---|---|---|
| Train | 2023-09-01 | 2024-09-01 |
| Validation | 2024-09-01 | 2024-11-01 |
| Test | 2024-11-01 | 2025-01-01 |

Use fingerprint version `nfc-casefold-whitespace-sha256-v1`:

1. normalize the staging narrative to Unicode NFC;
2. apply Unicode case folding;
3. split on Unicode whitespace and rejoin tokens with one ASCII space; and
4. hash the UTF-8 bytes with SHA-256.

Group the full eligible population before assigning a split.

- If one fingerprint has multiple target labels, exclude every row in that
  group as `duplicate_label_conflict`.
- Otherwise retain one canonical row: the earliest `date_received`, then the
  lowest complaint ID, raw batch ID, and source-row ordinal as deterministic
  tie-breakers.
- Exclude every other row in that group as `duplicate_same_label`.
- Assign the canonical row only from its own receipt date. Never move a later
  row into an earlier partition.

The test partition remains untouched during tuning. CT-204 may report its
majority baseline only because that baseline has no tunable parameters. Later
model or threshold selection must use train and validation only until the final
test evaluation gate.

## Measured approval evidence

The approved diagnostic projected 561,342 canonical rows:

| Split | Rows | Share | Rarest class |
|---|---:|---:|---:|
| Train | 394,564 | 70.289% | 1,173 |
| Validation | 80,992 | 14.428% | 227 |
| Test | 85,786 | 15.282% | 416 |

It projected 316,206 `duplicate_same_label` exclusions and 101,646
`duplicate_label_conflict` exclusions. These are discovery measurements; the
versioned CT-203 command must reproduce and reconcile them before they become
accepted run evidence.

## Persistence and privacy

Store append-only split runs and one disposition per eligible row. Split
outcomes may contain lineage, the derived fingerprint, assignment, and closed
exclusion reason. They must not copy narrative text, complaint IDs, company,
location, or other source values into the analytical split tables.

The commit-safe manifest contains only versions, boundaries, aggregate counts,
checks, and lineage. Individual fingerprints, row identities, complaint IDs,
and narratives remain local and governed by ADR 0009.

## Limitations

Version `1.0.0` does not perform fuzzy or semantic near-duplicate detection.
Removing punctuation, numbers, or approximate token matches could merge
materially different complaints and introduce an opaque data-selection rule.
Near-duplicate analysis may be proposed later using training data first, but it
must not inspect test outcomes during model tuning or silently change this
version.

## Approval

Charles explicitly approved these boundaries, the normalized fingerprint,
canonical-earliest rule, complete conflicting-label exclusion, and the v1 fuzzy
matching limitation on 2026-07-23.
