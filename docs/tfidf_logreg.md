# TF-IDF logistic-regression baseline

CT-205 implements the accepted rule in ADR 0011. It selects one sparse linear
text classifier on validation data while leaving the temporal test partition
untouched.

## What the command does

The full command:

1. validates the accepted split manifest and requires a clean Git commit;
2. reads only included training and validation narratives from PostgreSQL;
3. reconciles both split totals and all eleven class counts to the manifest;
4. fits the frozen TF-IDF vocabulary on training narratives only;
5. transforms validation without changing that vocabulary;
6. fits the four accepted logistic candidates sequentially;
7. excludes non-converged candidates and applies the ordered validation rule;
8. atomically saves the selected pipeline under ignored `artifacts/`; and
9. writes a closed, aggregate-only JSON report under
   `data/evaluations/cfpb/tfidf-logreg/`.

There is intentionally no test query or test metric in CT-205.

## Why these components

TF-IDF turns a narrative into a sparse vector whose weights increase for terms
important to that narrative and decrease for terms common across the corpus.
Adding bigrams lets the baseline distinguish short phrases such as “credit
report” while retaining single-word evidence. L2 normalization keeps document
length from becoming the dominant signal.

Multinomial logistic regression learns one linear decision surface per product
route. It is a strong baseline for sparse text, produces class probabilities,
and is easier to inspect and serve than a transformer. `saga` supports sparse
multiclass optimization. L2 regularization reduces overfitting by shrinking
weights; `C` is inverse regularization strength, so `0.5` regularizes more than
`1.0`.

`class_weight="balanced"` increases the loss contribution of rare labels. It
can improve rare-class recall, but may reduce overall precision or weighted F1.
That trade-off is measured rather than assumed.

## Run the training-only smoke check

Start PostgreSQL and verify that the accepted real run is present. Then run:

```powershell
.\.venv\Scripts\complaint-triage.exe train-tfidf-logreg `
  --split-manifest data/manifests/cfpb/splits/<run-id>-split-1.0.0.json `
  --smoke
```

Smoke mode selects up to 100 training rows per class. It uses `min_df=1` only
because the bounded execution check is too small for the full frequency
threshold. It fits the first candidate solely to prove the executable path.
It does not access validation or test, compare candidates, write a report, or
retain a pipeline. It is not evaluation evidence.

## Run the accepted selection

The full run must start from a clean implementation commit:

```powershell
.\.venv\Scripts\complaint-triage.exe train-tfidf-logreg `
  --split-manifest data/manifests/cfpb/splits/<run-id>-split-1.0.0.json
```

The command loads about 475,000 narratives and builds float64 sparse matrices,
so it can take substantial time and memory. Candidates are fitted sequentially
to avoid holding four estimators in training at once. Do not interrupt the
process while it is publishing the selected artifact or report.

Rerunning after success verifies the report identity and artifact hash instead
of silently replacing evidence. A missing or changed artifact fails closed.

## Read the selection report

Start with:

- `selection.selected_candidate_id` for the winner;
- each candidate's `converged` and `n_iter` values;
- validation `macro_f1` for balanced route quality;
- `worst_class_recall` for the weakest route;
- `weighted_f1` and accuracy for volume-weighted context; and
- per-class precision, recall, F1, support, and the confusion matrix for where
  the routing errors concentrate.

Macro F1 gives every product equal weight. Weighted F1 gives high-volume
products more influence. Worst-class recall exposes a route the averages might
hide. None of these validation metrics is a final test claim because validation
was used to choose the model.

## Data leakage controls

The vectorizer calls `fit_transform` only on training text and calls
`transform` on validation. The loader's full-run SQL permits only the literal
set `train, validation`; smoke SQL permits only `train`. The model-selection
module has no test-data input. Tests include a validation-only sentinel token
and assert that it is absent from the fitted vocabulary.

## Artifact handling

The `.joblib` file contains the learned vocabulary and model coefficients. It
is ignored by Git but is still governed real-data material:

- keep it only on this machine;
- do not commit, upload, sync, or back it up;
- do not print vocabulary tokens or token-linked coefficients; and
- delete it with the retained raw/staged data no later than 2026-11-19 unless a
  new retention decision is approved.

The JSON report is commit-safe because its closed schema excludes row values,
narratives, complaint IDs, vocabulary, and token-linked explanations.

## Failure behavior

The command returns a safe error code without source values when configuration,
manifest validation, source reconciliation, taxonomy completeness, database
access, convergence, artifact publication, report validation, or replay
verification fails. A failure is not permission to widen the candidate search,
read test data, or publish partial metrics.

## Verification

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
```

PostgreSQL integration tests remain opt-in:

```powershell
$env:RUN_POSTGRES_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest
```
