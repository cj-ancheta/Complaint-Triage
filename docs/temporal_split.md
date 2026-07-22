# Temporal split and duplicate isolation

CT-203 implements accepted ADR 0010 as split version `1.0.0`. It creates a
future-facing analytical split only after the complete eligible population for
one extraction run exists.

## Approved boundaries

```text
train:      2023-09-01 <= date_received < 2024-09-01
validation: 2024-09-01 <= date_received < 2024-11-01
test:       2024-11-01 <= date_received < 2025-01-01
```

Whole months make the periods easy to explain and reproduce. The test period is
the latest two months and must remain untouched during later tuning. A majority
baseline may be evaluated there because it has no fitted or selected parameter;
later model, calibration, and abstention decisions must use training and
validation data until final evaluation.

## Duplicate rule

The command reads eligible narratives locally from staging and computes
fingerprint `nfc-casefold-whitespace-sha256-v1`:

1. Unicode NFC normalization;
2. Unicode case folding;
3. Unicode whitespace collapse to one ASCII space; and
4. SHA-256 over UTF-8 bytes.

It does not remove punctuation or numbers and does not perform fuzzy semantic
matching. This conservative boundary catches presentation-only variants without
claiming that merely similar complaints are equivalent.

The full run is grouped before time assignment. A same-label group retains only
its earliest row; later repetitions are `duplicate_same_label`. A group with
multiple target labels is entirely `duplicate_label_conflict`. Only retained
canonical rows receive train, validation, or test assignments.

## Storage

`analytical.split_runs` stores the immutable rule identity, source lineage,
boundaries, and reconciled counts. `analytical.split_outcomes` stores local row
lineage, disposition, assignment or exclusion reason, and the derived
fingerprint. It does not copy narrative text or complaint IDs.

The generated JSON under `data/manifests/cfpb/splits/` is safe to commit. It
contains only aggregate counts, versions, boundaries, lineage, and boolean
checks. Individual fingerprints and row identities remain in local PostgreSQL
under ADR 0009.

## Run the split

Apply current migrations, make sure the repository is at a clean implementation
commit, and run:

```powershell
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\complaint-triage.exe build-temporal-split `
  --run-manifest data/manifests/cfpb/runs/<run-id>.json
```

The first build requires a clean Git commit and records its SHA. An idempotent
rerun verifies stored identity and regenerates the same manifest without
rewriting append-only rows.

## Fail-closed checks

The command refuses to publish unless:

- all 16 source batches contribute eligible rows;
- every eligible row has exactly one split disposition;
- inclusion and exclusion totals reconcile;
- train, validation, and test totals reconcile to included rows;
- every included fingerprint is unique;
- every included row falls inside its assigned date interval; and
- all three splits are non-empty.

Errors contain stable codes and aggregate details only. Narratives, complaint
IDs, and individual fingerprints are never printed.

## Verify

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
$env:RUN_POSTGRES_TESTS = "1"
.\.venv\Scripts\pytest.exe -q
```

The PostgreSQL tests use synthetic narratives and prove normalization,
canonical-earliest selection, label-conflict exclusion, no fingerprint overlap,
idempotency, rollback, database constraints, and append-only behavior.
