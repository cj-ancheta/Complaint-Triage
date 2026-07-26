# Publication readiness record

Status: `internal_draft_complete_external_publication_not_authorized`

Review date: 2026-07-26

Accepted research-evidence snapshot:
`2d886756227787b2eed2d5f46754b2ab8fd7745b`

## Readiness matrix

| Gate | Evidence | Result |
|---|---|---|
| QA evidence accepted | 119 checks replayed; 13 findings resolved; accepted conclusion `pass` | pass |
| Manuscript complete | 5,000-8,000 words; abstract through declarations; RQ1-RQ4 answered | pass |
| Literature traceability | 22 verified sources mapped to 23 planned claims with scope caveats | pass |
| Numerical traceability | T1-T6 generated; main result tables synchronized from seven hashed aggregate sources | pass |
| Figure traceability | F1-F6 deterministic SVG; aggregate sources only; source manifest committed | pass |
| Citation coverage | every paper-local reference ID cited by the manuscript | pass |
| Privacy boundary | no narratives, complaint IDs, row values, vocabulary, or row-level predictions | pass |
| Frozen-test boundary | count may be described; no frozen-test performance is reported | pass |
| Deployment boundary | no model API, threshold, routing, or deployment is authorized | pass |
| Editorial owner review | final wording, venue/template, and author presentation not yet approved | pending |
| Public metric promotion | QA release boundary remains `public_metric_promotion_authorized: false` | blocked |

## Deterministic reproduction

From the repository root:

```powershell
.\.venv\Scripts\python.exe paper\scripts\generate.py --check
.\.venv\Scripts\python.exe -m pytest tests\test_paper_plan.py tests\test_paper_tables.py -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

The generator reads committed aggregate JSON and Markdown metadata only. It
does not connect to PostgreSQL or inspect `data/raw` or `artifacts`. Its source
manifest canonicalizes line endings before hashing so Windows and Linux checks
agree.

## Decision

The research package is complete enough for internal editorial review and a
portfolio-paper design pass. This record does not authorize external publication
or reinterpret the validation metrics as final performance. External release
requires an explicit owner decision that preserves the validation-only banner,
the negative abstention result, the frozen-test statement, privacy exclusions,
and all material limitations.

No deployment, routing, frozen-test access, or new threshold search is required
to complete editorial review.
