# Generated validation result tables

Status: deterministic aggregate output; validation-only

These tables are generated from the committed JSON listed in
`source_manifest.json`. Do not edit them manually.

## T1. Governed cohort flow

| Cohort stage | Records | Role or disposition |
|---|---:|---|
| Structurally staged | 979,995 | input |
| English eligible | 979,194 | 801 language exclusions |
| Canonical included | 561,342 | after duplicate isolation |
| Train | 394,564 | model fitting |
| Validation | 80,992 | model and policy tuning |
| Frozen test | 85,786 | sealed; no paper performance |

*Aggregate cohort evidence; frozen-test performance is not accessed.*

## T2. Validation model comparison

| Metric | Majority reference | TF-IDF | MiniLM | MiniLM - TF-IDF |
|---|---:|---:|---:|---:|
| Accuracy | 0.666881 | 0.883692 | 0.885853 | +0.002161 |
| Macro F1 | 0.072741 | 0.699661 | 0.735746 | +0.036085 |
| Weighted F1 | 0.533607 | 0.879291 | 0.886692 | +0.007401 |
| Worst-class recall | 0.000000 | 0.057269 | 0.207048 | +0.149779 |

*Validation-only comparison; the frozen test is not reported.*

## T3. Per-class validation comparison

| Class | Support | TF-IDF F1 | TF-IDF recall | MiniLM F1 | MiniLM recall | F1 winner |
|---|---:|---:|---:|---:|---:|---|
| Checking or savings account | 4,961 | 0.826354 | 0.853255 | 0.834767 | 0.841161 | transformer |
| Credit card | 5,195 | 0.770649 | 0.764196 | 0.777558 | 0.793648 | transformer |
| Credit reporting or other personal consumer reports | 54,012 | 0.941373 | 0.960675 | 0.942451 | 0.932793 | transformer |
| Debt collection | 8,784 | 0.723931 | 0.679303 | 0.752423 | 0.764458 | transformer |
| Debt or credit management | 227 | 0.106996 | 0.057269 | 0.277286 | 0.207048 | transformer |
| Money transfer, virtual currency, or money service | 1,684 | 0.690515 | 0.624703 | 0.723480 | 0.720903 | transformer |
| Mortgage | 2,036 | 0.876339 | 0.884086 | 0.873574 | 0.921415 | baseline |
| Payday loan, title loan, personal loan, or advance loan | 905 | 0.534228 | 0.439779 | 0.597171 | 0.629834 | transformer |
| Prepaid card | 452 | 0.672000 | 0.557522 | 0.726667 | 0.723451 | transformer |
| Student loan | 1,481 | 0.882227 | 0.834571 | 0.884273 | 0.905469 | transformer |
| Vehicle loan or lease | 1,255 | 0.671655 | 0.607968 | 0.703557 | 0.780080 | transformer |

*Validation-only class metrics in immutable taxonomy order.*

## T4. October temperature-scaling assessment

| October diagnostic | Before | After | Change |
|---|---:|---:|---:|
| Accuracy | 0.882121 | 0.882121 | +0.000000 |
| Mean top-label confidence | 0.905545 | 0.898805 | -0.006739 |
| Confidence minus accuracy | 0.023424 | 0.016685 | -0.006739 |
| Negative log likelihood | 0.371454 | 0.369804 | -0.001650 |
| Multiclass Brier loss | 0.177733 | 0.177053 | -0.000680 |
| Equal-width ECE, 15 bins | 0.023894 | 0.017336 | -0.006558 |
| Equal-mass ECE, 15 bins | 0.023598 | 0.017946 | -0.005652 |

*Validation-only tuning evidence from October.*

## T5. Representative abstention failures

| Threshold | Coverage | Review rate | Selective accuracy | False suggestion rate | Blocking evidence |
|---:|---:|---:|---:|---:|---|
| 0.75 | 0.856279 | 0.143721 | 0.936402 | 0.054457 | false suggestions exceed 0.05; least-suggested class has 4 cases |
| 0.80 | 0.825440 | 0.174560 | 0.945032 | 0.045373 | least-suggested class has 0 cases; predicted-class precision gate fails |

*Validation-only policy evidence; neither threshold was eligible.*

## T6. Accepted repository QA findings

### Severity

| Severity | Findings |
|---|---:|
| Critical | 0 |
| High | 3 |
| Medium | 7 |
| Low | 3 |

### Control family

| Control family | Findings | Accepted status |
|---|---:|---|
| ci | 1 | resolved |
| data_governance | 1 | resolved |
| database | 1 | resolved |
| governance_metadata | 1 | resolved |
| maintainability | 1 | resolved |
| repository | 1 | resolved |
| reproducibility | 1 | resolved |
| security | 2 | resolved |
| serialization | 1 | resolved |
| testing | 1 | resolved |
| typing | 1 | resolved |
| warnings | 1 | resolved |

*Repository assurance evidence; not a model-validity measure.*
