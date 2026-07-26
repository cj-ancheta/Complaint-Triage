# Publication readiness record

Status: `publication_ready_public_preprint_authorized`

Release version: `1.0.0`

Review date: 2026-07-26

Accepted research-evidence snapshot:
`2d886756227787b2eed2d5f46754b2ab8fd7745b`

## Readiness matrix

| Gate | Evidence | Result |
|---|---|---|
| QA evidence accepted | 119 checks replayed; 13 findings resolved; accepted conclusion `pass` | pass |
| Manuscript complete | 5,000-8,000 words; abstract through declarations; RQ1-RQ5 answered | pass |
| Literature traceability | 30 verified sources mapped to 29 planned claims with scope caveats | pass |
| Numerical traceability | T1-T6 generated; main result tables synchronized from seven hashed aggregate sources | pass |
| Figure traceability | F1-F7 deterministic SVG; aggregate sources or prospective design only; source manifest committed | pass |
| Citation coverage | every paper-local reference ID cited by the manuscript | pass |
| Privacy boundary | no narratives, complaint IDs, row values, vocabulary, or row-level predictions | pass |
| Frozen-test boundary | count may be described; no frozen-test performance is reported | pass |
| Deployment boundary | no model API, threshold, routing, or deployment is authorized | pass |
| Causal boundary | no observed causal effect is claimed; target trial is explicitly not registered or conducted | pass |
| Impact communication | plain-language statement separates the consequential no-go result from unmeasured workflow effects | pass |
| Editorial owner review | owner authorized finalization and publication on 2026-07-26 | pass |
| Bounded public reporting | paper and validation-labelled metrics authorized for preprint release | pass |
| Final-performance promotion | QA field remains `public_metric_promotion_authorized: false`; no metric is presented as frozen-test or production performance | pass |

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

The owner explicitly authorized external publication as a public preprint on
2026-07-26. The authorization covers the paper, deterministic figures, causal
design blueprint, and validation-labelled metrics. It does not reinterpret the
metrics as final performance or authorize the proposed causal trial.

Release must preserve the validation-only banner, negative abstention result,
frozen-test statement, privacy exclusions, not-conducted causal-study status,
and all material limitations. No deployment, routing, frozen-test access, model
exposure, or new threshold search is authorized.
