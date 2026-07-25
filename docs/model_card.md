# Calibrated MiniLM Complaint Classifier Model Card

- Model-card version: `1.0.0`
- Research run: `cfpb-run-20260722T130728Z-2b7815d4c850`
- Training report: `transformer-minilm-selection-1.0.0`
- Selected checkpoint: epoch 3
- Base encoder: `microsoft/MiniLM-L12-H384-uncased`
- Base revision: `9a201d7b3ebebc5feabf9fbb4b3a4ec5d3f2440d`
- Calibration: scalar temperature `1.041049944456901`
- Operational threshold: none
- Current operating status: `manual_review_only`

## Model description

The candidate is an eleven-class, fully fine-tuned MiniLM sequence classifier.
It accepts only the consumer complaint narrative, tokenizes at a maximum length
of 384 model tokens, and outputs one score per accepted CFPB product class. A
single scalar temperature calibrates the logits without changing the argmax
class ranking.

The model artifact and calibrator are governed local files and are excluded from
Git. Their hashes are carried through the accepted aggregate evidence. This card
does not make the artifacts public or authorize an API.

## Intended uses

The intended research use is to study a possible human-review aid for assigning
one current CFPB product label to an English complaint narrative. If a later
policy, final evaluation, service, security review, and release approval all
pass, a reviewer could see a non-binding suggestion and calibrated confidence
while retaining authority to correct or escalate it.

The currently authorized use is narrower: offline research, aggregate
evaluation, governance review, and portfolio discussion of why the candidate
was not authorized for automated routing.

## Prohibited uses

Do not use the model to:

- automatically route, close, reject, prioritize, or deprioritize complaints;
- determine truth, liability, legal merit, compensation, vulnerability, fraud,
  creditworthiness, or company misconduct;
- generate response wording or business justification;
- operate outside the eleven-label taxonomy or on unsupported languages;
- evaluate individual consumers, employees, companies, or demographic groups;
- interpret confidence as the probability that a narrative is truthful or that
  a business action is correct;
- expose narrative-derived explanations or training vocabulary publicly; or
- claim production, final-test, fairness, productivity, or impact performance.

## Training and evaluation data

Training uses 394,564 duplicate-isolated English narratives received from
2023-09-01 through 2024-08-31. Validation contains 80,992 narratives from
2024-09-01 through 2024-10-31. September's 39,161 validation rows fit the
temperature; October's 41,831 rows assessed calibration and the fixed
abstention grid. The 85,786-record November–December test partition remains
untouched.

The target distribution is highly imbalanced. Training support for Debt or
credit management is 1,173 versus 248,062 for credit reporting. See the
[`data_sheet.md`](data_sheet.md) for source, exclusion, duplicate, retention,
and representativeness details.

## Evaluation evidence

All figures below are internal validation evidence, not final or approved
public-performance claims.

On the complete 80,992-record validation partition, selected epoch 3 produced:

| Metric | MiniLM | TF-IDF reference | Difference |
|---|---:|---:|---:|
| Accuracy | 0.885853 | 0.883692 | +0.002161 |
| Macro F1 | 0.735746 | 0.699661 | +0.036085 |
| Weighted F1 | 0.886692 | 0.879291 | +0.007401 |
| Worst-class recall | 0.207048 | 0.057269 | +0.149779 |

MiniLM had higher per-class F1 for ten classes; TF-IDF retained the Mortgage F1
lead. The rarest validation class, Debt or credit management, remained weak:
MiniLM precision was 0.419643, recall 0.207048, and F1 0.277286 on 227 records.
This is a material limitation, not a solved fairness result.

After calibration, October accuracy was 0.882121, NLL 0.369804, multiclass
Brier loss 0.177053, equal-width ECE 0.017336, and equal-mass ECE 0.017946.
Temperature scaling improved aggregate NLL, Brier, and ECE without changing
argmax predictions, but several class-level probability/prevalence gaps moved
slightly in the wrong direction. A single temperature is not class-specific
calibration.

## Abstention evidence

ADR 0016 tested thresholds `0.50` through `0.95` on October under fixed global
and class-aware gates. No threshold qualified. Two examples show why:

| Threshold | Coverage | Selective accuracy | False suggestion rate | Blocking evidence |
|---:|---:|---:|---:|---|
| 0.75 | 0.856279 | 0.936402 | 0.054457 | False suggestions exceeded 0.05; least-suggested class had 4 predictions |
| 0.80 | 0.825440 | 0.945032 | 0.045373 | One predicted class had zero suggestions and therefore zero qualifying precision |

The class-aware gates intentionally prevented attractive aggregate performance
from hiding exclusion of a rare route. The accepted fallback is
`manual_review_only`; there is no approved threshold.

## Operational evidence

On one Windows 11 laptop with an Intel Core Ultra 7 255HX, a fixed CPU workload
of 512 October narratives repeated three times measured MiniLM p50 latency at
48.2386 ms, p95 at 83.9696 ms, maximum at 111.1995 ms, model load at 4.187569 s,
peak working set at 1,003,794,432 bytes, and model-plus-calibrator footprint at
133,481,428 bytes. This is a single-device benchmark, not service latency,
throughput, concurrency, cloud cost, or an SLA.

Training used a local CUDA environment and approximately 5,292.732 summed
training-plus-validation seconds across three epochs. Energy use and carbon
emissions were not measured.

## Explainability

Approved evidence is global: validation metrics, class-level error rates,
aggregate confusion matrices, calibration diagnostics, and threshold trade-offs.
Local transformer attributions, attention-as-explanation, causal reason claims,
and narrative-derived reason codes are not authorized. Model evidence must not
be presented as a business justification.

## Fairness and ethical considerations

No protected attributes were used or evaluated. Class, month, length, and rarity
slices cannot establish demographic fairness. Public complaint data can encode
unequal access, reporting behavior, institutional processes, historical bias,
and taxonomy choices. Errors can delay review; confidence can amplify automation
bias; and weak rare-class behavior can concentrate harm. Human review and class-
aware gates reduce some risk but do not demonstrate equitable outcomes.

## Limitations

- No frozen-test estimate exists.
- Validation influenced epoch selection, calibration assessment, model choice,
  and threshold analysis.
- No threshold passed the approved operating policy.
- The rarest class remains difficult and disappears from high-confidence
  predictions at otherwise attractive global thresholds.
- Inputs longer than 384 tokens are truncated.
- English detection and CFPB labels are imperfect proxies, not ground truth.
- Semantic near-duplicates and distribution shifts can remain.
- Reviewer productivity, override behavior, downstream harm, service security,
  concurrency, monitoring, and real deployment cost were not measured.

## Maintenance plan

No model is active in a service. Before any future activation, the owner must
approve a threshold policy, preserve a locked evaluation boundary, complete the
promotion checklist, implement security and oversight controls, and approve a
deployment target. Once active, monitoring would need input validity, taxonomy,
class distribution, narrative length, confidence, abstention, override, and
label-delay signals with predeclared warning and stop boundaries.

Retraining requires a new model version, data/split lineage, candidate comparison,
calibration, threshold policy, governance review, and frozen evaluation. It must
not overwrite this evidence or tune on the current frozen test.

## Release status

**Not authorized for automated routing, frozen-test access, deployment, or
public metric promotion.** The only accepted operating outcome is
`manual_review_only`. CT-402 is closed as `not applicable` for this run because
no threshold qualified; the frozen test remains sealed. Any future attempt
requires a new threshold policy proposed and approved without using test
outcomes. See the
[`governance_pack.md`](governance_pack.md) for the consolidated release decision.
