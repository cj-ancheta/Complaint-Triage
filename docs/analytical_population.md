# Analytical population report

## Purpose

CT-202 turns staging outcomes into a versioned eligibility funnel without
selecting temporal splits or training a model. Charles accepted the policy in
[`ADR 0008`](decisions/0008-proposed-analytical-population.md) on 2026-07-22.

## Implemented contract

Population version `1.0.0` is bound to:

- staging transformation `1.1.0`;
- taxonomy `cfpb-product-2023-08-24`;
- `2023-09-01 <= date_received < 2025-01-01`;
- eleven identity-mapped product labels;
- the exact installed Lingua 2.2.x detector in all-language high-accuracy mode;
  and
- the closed exclusion vocabulary in ADR 0008.

Every staged input produces one analytical outcome. Database checks enforce:

```text
input = output = eligible + excluded
```

Outcome rows contain no narrative or complaint identifier. They retain only the
staging row key, population version, eligibility, reason codes, eligible target,
detected language code, and narrative character count.

## Install and migrate

The new detector is a compiled dependency and requires Python 3.12 or newer:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Migration `0003_analytical_population` creates the append-only `analytical`
schema. The normal migration command succeeded locally on 2026-07-22.

## Run a report

The raw batch must already have a completed staging `1.1.0` outcome set:

```powershell
.\.venv\Scripts\python.exe -m complaint_triage report-population `
  --batch-id cfpb-YYYYMMDDTHHMMSSZ-aaaaaaaaaaaa
```

The command is idempotent. A first successful call returns `status: reported`;
the same identity later returns `status: already_reported` after verifying the
stored header and outcome counts.

Important report fields:

- `counts`: reconciled input, eligible, excluded, and output rows;
- `exclusion_reason_counts`: occurrences of each reason, which can exceed the
  excluded row count because a row can have multiple structural reasons;
- `eligible_counts_by_product`: post-filter class support;
- `detected_language_counts`: languages computed only after structural checks;
- `language_evaluated_record_count`: rows actually sent to the detector,
  including undetermined results;
- `eligible_narrative_length`: minimum, maximum, and mean character length; and
- `privacy`: explicit confirmation that narratives are absent from output and the
  analytical schema.

Errors return controlled codes without source values. An unknown or unstaged
batch returns `staging_batch_not_found` and does not create a partial run.

## Synthetic verification result

The PostgreSQL integration test uses five visibly synthetic rows and proves:

- one eligible English/current-taxonomy/in-window row;
- one pre-window exclusion;
- one unknown-product exclusion;
- one Spanish-language exclusion;
- one staging-quarantined exclusion;
- forced failure on the second insert rolls back both header and outcomes;
- replay inserts nothing and returns the same aggregate report;
- unknown reason codes violate a database check; and
- update and delete attempts fail against append-only triggers.

These counts are test evidence, not CFPB measurements. The repository still has
no real raw complaint batch. ADR 0009 now approves a bounded local retention
policy, but real ingestion remains technically blocked until the next extraction
issue implements and tests its expiry and cleanup controls. Consequently, CT-202
does not claim real post-filter class counts or language/length distributions.

## Operational limitations

- Lingua classification is fallible and must be reviewed on a bounded sample
  before modelling claims are made.
- The report streams database rows in batches of 1,000 but language detection on
  a large extract can still take substantial CPU time.
- The exact detector version is part of population identity; upgrading the
  package requires a new population version.
- An eligible result does not mean a row is safe from cross-time duplicate
  leakage. CT-203 owns that rule.
- Do not sum reason counts to infer excluded rows; use the reconciled status
  counts.
