# Table and figure plan

Every value must be generated from the listed committed aggregate source.

## Main-text tables

| ID | Content | Source | Purpose |
|---|---|---|---|
| T1 | Cohort flow from staged to canonical split | run report and split manifest | make exclusions and frozen partition visible |
| T2 | Majority, TF-IDF, and MiniLM validation metrics | majority and model-comparison reports | show why accuracy alone is misleading |
| T3 | Per-class support, F1, recall, and model winner | model-comparison report | expose rare-class behavior |
| T4 | October calibration before/after | calibration report | separate confidence quality from classification accuracy |
| T5 | Representative abstention thresholds and failed gates | abstention report | explain the negative policy result |
| T6 | QA findings by severity/control family | QA findings and evidence | connect engineering controls to evidentiary confidence |

## Main-text figures

| ID | Visual | Source | Design rule |
|---|---|---|---|
| F1 | Governed evidence pipeline | manifests and QA plan | architecture flow; no row examples |
| F2 | Training/validation class support | split manifest | horizontal log-scale bars with exact counts |
| F3 | Per-class MiniLM minus TF-IDF F1 | comparison report | zero-centered dot/bar plot; retain Mortgage loss |
| F4 | October reliability before/after calibration | calibration report | plot committed equal-width bins; show empty bins |
| F5 | Coverage versus selective accuracy with gate failures | abstention report | label ineligible thresholds; no “optimal” language |
| F6 | QA remediation timeline | Git/QA evidence | distinguish code controls from model evidence |

## Appendices

- Full confusion matrices for majority, TF-IDF, and MiniLM.
- All eleven per-class calibration summaries.
- All candidate thresholds, counts, Wilson intervals, and six gate results.
- Exact environment identities, lock filenames, and accepted evidence hashes.

## Generation requirements

- Add one deterministic script under `paper/scripts/` in the next phase.
- Read only committed JSON and Markdown metadata; never connect to PostgreSQL or
  inspect `data/raw` or `artifacts`.
- Emit Markdown/CSV/SVG or PNG under `paper/generated/` with a source manifest.
- Sort labels by the immutable taxonomy order and thresholds numerically.
- Use colorblind-safe palettes and never rely on color alone for pass/fail.
- Include “validation-only” in captions for every model-result table or figure.
- Test exact row counts, source hashes, and prohibited fields before generation.
