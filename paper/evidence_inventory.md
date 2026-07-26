# Paper evidence inventory

Evidence snapshot: `2d886756227787b2eed2d5f46754b2ab8fd7745b`

All numerical evidence is aggregate, validation-only, and already committed.
The paper may describe these values as results within the retained research
run, but never as frozen-test, production, population-representative, or final
generalization performance.

Frozen-test access is not authorized; the test partition is described only by
its committed aggregate manifest metadata.

## Data and cohort evidence

| Evidence | Accepted source | Paper use | Mandatory limitation |
|---|---|---|---|
| Sixteen monthly source shards and acquisition lineage | `data/manifests/cfpb/runs/cfpb-run-20260722T130728Z-2b7815d4c850.json` | source window and reproducible acquisition design | public complaints are not a random sample |
| Reconciled raw, staging, and population counts | `data/manifests/cfpb/reports/cfpb-run-20260722T130728Z-2b7815d4c850.json` | cohort-flow table | language filtering and source labels are imperfect |
| Population rules and exclusions | `docs/data_sheet.md`, `docs/analytical_population.md` | feature, target, language, and privacy method | narrative-only English cohort is narrower than the source |
| Duplicate-isolated temporal split | `data/manifests/cfpb/splits/cfpb-run-20260722T130728Z-2b7815d4c850-split-1.0.0.json` | train/validation/test design and class support | exact normalization does not detect semantic duplicates |
| Taxonomy identity and stability | `docs/cfpb_taxonomy_stability.md` | eleven target classes and drift context | taxonomy choice is operational, not natural ground truth |

Key aggregate counts suitable for the methods section are 979,995 staged
records, 979,194 English-eligible records, 561,342 canonical included records,
394,564 training records, 80,992 validation records, and an untouched 85,786
record test partition. The 417,852 duplicate-related exclusions must be
explained rather than hidden as ordinary cleaning loss.

## Modelling evidence

| Evidence | Accepted source | Permitted interpretation |
|---|---|---|
| Training-majority reference | `data/evaluations/cfpb/majority/cfpb-run-20260722T130728Z-2b7815d4c850-majority-baseline-1.0.0.json` | demonstrates why accuracy is inadequate under imbalance |
| TF-IDF candidate search | `data/evaluations/cfpb/tfidf-logreg/cfpb-run-20260722T130728Z-2b7815d4c850-tfidf-logreg-selection-1.0.0.json` | transparent classical reference selected on validation macro F1 |
| MiniLM epochs and selection | `data/evaluations/cfpb/transformer/cfpb-run-20260722T130728Z-2b7815d4c850-transformer-minilm-selection-1.0.0.json` | compact-transformer validation result and epoch-selection trace |
| Direct comparison | `data/evaluations/cfpb/model-comparison/cfpb-run-20260722T130728Z-2b7815d4c850-validation-model-comparison-1.0.0.json` | aggregate and per-class differences under one validation population |
| Baseline error slices | `data/evaluations/cfpb/error-analysis/cfpb-run-20260722T130728Z-2b7815d4c850-baseline-error-analysis-1.0.0.json` | descriptive month, length, rarity, and confusion patterns only |

The central comparison is intentionally multi-metric. MiniLM's validation
accuracy was 0.885853 versus 0.883692 for TF-IDF, while macro F1 differed by
0.036085 and worst-class recall by 0.149779. Per-class F1 favored MiniLM for ten
classes and TF-IDF for Mortgage. These are internal validation values and were
used in model selection.

## Calibration, operations, and abstention evidence

| Evidence | Accepted source | Permitted interpretation |
|---|---|---|
| Scalar temperature fit and October assessment | `data/evaluations/cfpb/calibration/cfpb-run-20260722T130728Z-2b7815d4c850-transformer-temperature-calibration-1.0.0.json` | aggregate probabilistic diagnostics after fixed temperature scaling |
| Fixed CPU benchmark and candidate gate | `data/evaluations/cfpb/model-selection/cfpb-run-20260722T130728Z-2b7815d4c850-operational-model-selection-1.0.0.json` | single-device feasibility comparison, not an SLA |
| Fixed abstention grid and class-aware gates | `data/evaluations/cfpb/abstention/cfpb-run-20260722T130728Z-2b7815d4c850-abstention-threshold-analysis-1.0.0.json` | negative selective-classification result and manual-review fallback |
| Policy definition | `docs/decisions/0016-proposed-abstention-and-final-evaluation-policy.md` | proves thresholds and gates were fixed before analysis |

Temperature `1.041049944456901` improved October aggregate NLL, Brier loss,
and both declared ECE summaries without changing predictions. This does not
mean every class became better calibrated. No tested abstention threshold passed
all global and class-aware requirements. The paper's operational conclusion is
therefore the negative result: the candidate was not authorized to suggest or
route complaints.

## Engineering and governance evidence

| Evidence | Accepted source | Paper use |
|---|---|---|
| Independent 119-check aggregate replay | `docs/qa/repository_qa_report.md` | evidentiary confidence and reproducibility method |
| Thirteen resolved QA findings | `docs/qa/qa_findings.json` | before/after software-assurance case study |
| Accepted QA evidence | `docs/qa/qa_evidence.json`, `docs/qa/qa_acceptance.md` | accepted snapshot and claim boundary |
| Reproducible environments | `docs/reproducible_environments.md`, `requirements/locks/` | exact dependency and platform method |
| CI and security controls | `docs/ci.md`, `docs/security_supply_chain.md` | independent runtime, type, schema, coverage, and security gates |
| Data/model governance | `docs/governance_pack.md`, `docs/model_card.md`, `docs/risk_register.md` | intended use, prohibited use, retention, and human oversight |

QA evidence supports a claim that the repository controls were implemented and
tested. It does not prove the absence of every vulnerability, bias, secret, or
future regression.

## Evidence that is intentionally unavailable

- Frozen-test predictions and metrics: not accessed because no threshold passed.
- Raw narratives and complaint identifiers: local governed data, never paper material.
- Demographic attributes: not collected or evaluated.
- Reviewer outcomes, productivity, overrides, or harms: no deployment or user study.
- Service throughput, concurrency, uptime, and cloud cost: no service exists.
- Observed causal effects of model assistance: no treatment assignment,
  reviewer outcome, or downstream outcome exists in the research cohort.
- Causal explanations or narrative examples: outside the authorized evidence boundary.

## Prospective causal design boundary

`paper/prospective_causal_protocol.md` is a design artifact, not an empirical
source. It defines the future intervention, control, assignment, outcomes,
estimands, assumptions, route-specific success rule, and safety stopping
conditions. F7 visualizes that proposed structure. Neither artifact adds an
observation to the accepted evidence snapshot or authorizes a reviewer study.
