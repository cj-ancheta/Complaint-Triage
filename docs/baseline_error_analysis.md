# Baseline error analysis

CT-206 turns the accepted CT-205 validation predictions into reproducible,
aggregate diagnostic evidence. It does not retrain the model, change model
selection, choose an abstention threshold, access test data, or publish
narrative examples.

## Why error analysis follows aggregate performance

A single macro F1 cannot show which routes fail, what they are confused with,
or whether performance changes across time and input length. CT-206 asks four
more useful questions:

1. Which product classes have the weakest precision, recall, and F1?
2. Which actual routes are most often assigned to which incorrect routes?
3. Does performance differ between the two validation months?
4. Does performance differ across fixed narrative-length bands or between rare
   and common classes?

These are descriptive operational diagnostics. They are not demographic
fairness evidence and do not explain why any individual complaint was
misclassified.

## Frozen analysis boundary

The command analyzes only included validation rows from September and October
2024. Its SQL contains the literal predicate
`split_assignment = 'validation'`; there is no test-data option.

The selected CT-205 artifact must match the path, size, SHA-256, and package
versions recorded in the accepted model report. Verification happens before
joblib deserialization. The pipeline is trusted only because its hash is
anchored in accepted, committed evidence.

The command then:

1. reconciles validation class counts to the CT-205 report;
2. scores narratives in bounded batches without persisting predictions;
3. reproduces CT-205 accuracy, macro F1, weighted F1, worst-class recall,
   per-class metrics, and confusion matrix exactly;
4. calculates overall top-2 accuracy as a supporting diagnostic;
5. creates closed temporal, length, and rarity slices; and
6. writes only a schema-validated aggregate JSON report.

## Fixed slices

Slice definitions are frozen before reading results.

### Calendar month

- `2024-09`
- `2024-10`

Two months are enough to detect a large short-term difference, but not enough
to establish a general trend or seasonality. That limitation is encoded in the
report.

### Narrative length

Length comes from the accepted staging-derived character count, not from model
tokens:

| Band ID | Characters |
|---|---:|
| `chars-1-499` | 1–499 |
| `chars-500-999` | 500–999 |
| `chars-1000-1999` | 1,000–1,999 |
| `chars-2000-3999` | 2,000–3,999 |
| `chars-4000-plus` | 4,000+ |

All eleven taxonomy labels remain in macro calculations for every slice. If a
class has zero support in a slice, its recall is reported as zero. Class support
is included so the reader can distinguish observed failure from missing
evidence.

### Rare and common classes

A rare class has less than 1% of the accepted training rows. The rule uses the
training counts in the split manifest and cannot change after seeing validation
performance. Rarity-group metrics are unweighted averages of the already
computed per-class precision, recall, and F1 values.

### Confusion pairs

The report ranks at most 20 non-diagonal actual-to-predicted pairs by:

1. descending error count;
2. actual-label text; and
3. predicted-label text.

Each pair includes its share of all validation errors and its share of errors
within the actual class. This makes a high-volume confusion distinguishable
from a class-specific failure.

## Metrics and interpretation

- **Accuracy** is the share of correctly routed validation rows.
- **Macro F1** gives each of the eleven product routes equal weight.
- **Weighted F1** weights each route by its validation support.
- **Worst-class recall** exposes the least-recalled route.
- **Top-2 accuracy** asks whether the actual route is among the two highest
  model probabilities. It is diagnostic only; CT-206 does not implement a
  two-route product behavior.

Validation was already used to select the CT-205 candidate. These metrics are
therefore useful for diagnosis but are not an unbiased final estimate. Test
remains reserved for the later once-only final comparison gate.

## Accepted measured evidence

The real CT-206 run from implementation commit `6f13507` scored all 80,992
validation rows in 21 seconds. It reproduced CT-205 exactly: 9,420 errors,
accuracy 0.883692, macro F1 0.699661, weighted F1 0.879291, and worst-class
recall 0.057269. Supporting top-2 accuracy is 0.965256. Test was not accessed.

### Largest confusion

The largest actual-to-predicted error is:

`Debt collection` → `Credit reporting or other personal consumer reports`

It occurs 2,436 times, representing 25.8599% of all validation errors and
86.4750% of the errors within the actual `Debt collection` class. The reverse
direction occurs 1,221 times and is the second-largest confusion. This is model
evidence of overlapping routing language, not proof that the source labels are
wrong or that the two business routes should be merged.

### Month comparison

| Month | Rows | Errors | Accuracy | Macro F1 | Weighted F1 | Worst recall | Top-2 accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2024-09 | 39,161 | 4,269 | 0.890988 | 0.710195 | 0.887161 | 0.051020 | 0.967749 |
| 2024-10 | 41,831 | 5,151 | 0.876862 | 0.689863 | 0.871909 | 0.062016 | 0.962922 |

October macro F1 is 0.020332 lower than September. Two months cannot establish
seasonality or long-run degradation, but the difference is large enough to keep
temporal monitoring in the later evaluation and deployment design.

### Narrative-length comparison

| Band | Rows | Macro F1 | Worst recall | Top-2 accuracy |
|---|---:|---:|---:|---:|
| 1–499 | 23,079 | 0.646155 | 0.030303 | 0.949868 |
| 500–999 | 20,991 | 0.709150 | 0.069767 | 0.966652 |
| 1,000–1,999 | 23,352 | 0.713584 | 0.054545 | 0.973364 |
| 2,000–3,999 | 10,397 | 0.748408 | 0.153846 | 0.976051 |
| 4,000+ | 3,173 | 0.633940 | 0.000000 | 0.972896 |

Macro F1 spans 0.633940–0.748408, a difference of 0.114468. The shortest band
has the lowest top-2 accuracy. The 4,000+ band's zero worst-class recall is based
on only four `Debt or credit management` rows, so it is a high-uncertainty
warning rather than a stable rate.

### Rare versus common classes

The fixed training-share rule classifies `Debt or credit management` and
`Prepaid card` as rare. Together they have only 679 validation rows.

| Group | Labels | Support | Macro precision | Macro recall | Macro F1 |
|---|---:|---:|---:|---:|---:|
| Rare | 2 | 679 | 0.829069 | 0.307395 | 0.389498 |
| Common | 9 | 80,313 | 0.809197 | 0.738726 | 0.768586 |

Rare-class precision is not the central problem; recall is. The rare/common
macro-F1 gap is 0.379088. CT-206 describes that limitation but does not reopen
the accepted CT-205 search or select a new weighting rule.

The accepted issue report is
`data/evaluations/cfpb/error-analysis/cfpb-run-20260722T130728Z-2b7815d4c850-baseline-error-analysis-1.0.0.json`.

## Run the command

PostgreSQL and the governed local pipeline must be available. The first real
report requires a clean implementation commit:

```powershell
.\.venv\Scripts\complaint-triage.exe analyze-baseline-errors `
  --model-report data/evaluations/cfpb/tfidf-logreg/<run-id>-tfidf-logreg-selection-1.0.0.json
```

The report is written under `data/evaluations/cfpb/error-analysis/`. A replay
validates and returns the existing report without rescoring source rows.

## Privacy and retention

The commit-safe report may contain taxonomy labels, month labels, fixed length
bands, class supports, metrics, confusion counts, hashes, versions, and closed
limitations. It must not contain narratives, complaint IDs, row identities,
vocabulary, token-linked coefficients, or row-level predictions.

The selected pipeline remains ignored, local-only, and governed through
2026-11-19. The aggregate CT-206 report may remain after governed row-level data
and the source-derived model artifact are deleted.

## Unavailable and deferred slices

- Submission channel is not present in the accepted staging contract, so CT-206
  records it as unavailable rather than re-extracting or inventing data.
- The accepted window is entirely after the August 2023 taxonomy transition,
  so a pre/post-transition comparison is not applicable.
- Calibration and abstention require separate declared methods and an approved
  operational threshold; CT-206 does not pre-empt those decisions.
- Narrative-level examples could reveal retained source text and are not
  published. Synthetic examples may be created later for teaching or UI work.

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
$env:RUN_POSTGRES_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest
```

Tests cover closed slice boundaries, stable confusion ranking, rarity rules,
hash-before-load behavior, safe errors, validation-only SQL, report privacy,
schema validation, and idempotent replay.
