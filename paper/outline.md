# Detailed paper outline

Research-question map: model comparison (RQ1), calibration (RQ2), selective
classification and abstention (RQ3), repository assurance (RQ4), and a
prospective causal evaluation of reviewer impact (RQ5). Each empirical results
subsection must use only the evidence listed below; RQ5 is answered as a design,
not an observed effect.

Evidence inputs: committed aggregate manifests and evaluation reports,
governance documents, the accepted QA snapshot, and primary literature entered
through the claim-to-source matrix. Literature needed: source context,
classification methods and metrics, calibration, selective prediction,
human-AI oversight, and reproducible research.

Target form: 6,000–8,500 word public preprint plus causal-protocol appendix.

## 1. Title page and abstract

The abstract should contain five moves: operational problem, governed temporal
design, compared methods, central validation/abstention result, and the
manual-review conclusion. It should not lead with accuracy or imply a final-test
estimate. Add 5–7 keywords covering complaint classification, imbalanced text
classification, calibration, selective classification, human oversight, and
reproducible ML.

## 2. Introduction

1. Explain complaint product triage as a high-volume, asymmetric multiclass
   decision-support problem.
2. Explain why majority-dominated accuracy can conceal weak rare-class behavior.
3. Motivate the combined question: model quality, confidence quality, coverage,
   and evidence trustworthiness.
4. State the five research questions from `README.md`.
5. State contributions narrowly: governed dataset construction, classical versus
   compact-transformer validation, calibration/selective-classification
   analysis, and repository assurance.

Literature needed: CFPB source context, imbalanced classification metrics,
selective prediction, and human-AI decision support.

## 3. Related work

### 3.1 Consumer complaint classification

Cover prior complaint-topic/product classification and how this study differs
in temporal splitting, duplicate isolation, calibration, and governance. Avoid
claiming novelty until the search matrix is complete.

### 3.2 Classical and pretrained text classifiers

Explain why TF-IDF logistic regression is a meaningful strong baseline and why
a compact pretrained encoder is an appropriate higher-capacity comparator.

### 3.3 Calibration and selective classification

Introduce temperature scaling, proper scoring rules, ECE limitations,
risk–coverage trade-offs, and class-aware failure under imbalance.

### 3.4 Human oversight and evidence governance

Distinguish advisory decision support from automation. Connect reproducibility,
documentation, and software assurance to the credibility of empirical results.

### 3.5 Prediction reporting and causal impact

Separate transparent predictive evaluation from intervention effects. Introduce
target-trial reasoning, prospective AI-intervention reporting principles, and
why external human-AI effect sizes do not transport to complaint review.

## 4. Data and governance

### 4.1 Source and observation window

Describe the CFPB database, 16 whole-month shards, acquisition date, and the
2023-09-01 through 2024-12-31 observation window. State non-representativeness
and publication-process limitations up front.

### 4.2 Analytical population

Report cohort flow, English-language filter, narrative-only feature boundary,
eleven product labels, excluded fields, and privacy rationale.

### 4.3 Duplicate isolation and temporal split

Define normalization/fingerprinting, conflict exclusion, canonical earliest
record retention, and train/validation/frozen-test dates. Explain why the
frozen test remained sealed.

### 4.4 Retention and ethical boundary

Describe local-only raw data, deletion deadline, prohibited redistribution,
non-goals, and absence of demographic fairness evidence.

## 5. Methods

### 5.1 Evaluation priorities

Define accuracy, macro F1, weighted F1, per-class precision/recall/F1, and
worst-class recall. Explain why macro and worst-class measures are decision
criteria rather than decorative diagnostics.

### 5.2 Majority and TF-IDF references

Specify the training-majority reference and TF-IDF/logistic candidate grid,
convergence requirement, and ordered validation selection rule.

### 5.3 Compact MiniLM classifier

Specify pinned base model/revision, maximum 384 tokens, narrative-only input,
class weighting, batch probing, early stopping, and ordered epoch selection.

### 5.4 Temperature scaling

Specify September fit, October assessment, scalar temperature objective,
probability metrics, prediction invariance, and class-level limitations.

### 5.5 Fixed abstention policy

Define threshold grid, coverage/review/selective metrics, six eligibility gates,
and ordered selection rule. State that these rules were committed before the
real threshold analysis.

### 5.6 Reproducibility and QA protocol

Describe exact locks, independent standard/CPU-transformer jobs, PostgreSQL
schema controls, coverage/warning ratchets, security gates, strict typing,
artifact trust, and independent aggregate evidence replay.

### 5.7 Prospective causal evaluation

Specify the reviewer-level causal question, contamination-aware randomization,
manual-only control, suggestion-interface intervention, intention-to-treat
estimands, independent adjudication, route-specific constraints, and the
not-conducted boundary.

## 6. Results

### 6.1 Cohort and class imbalance

Present cohort flow and log-scale class support. Highlight the majority class
and rarest class without implying demographics.

### 6.2 Model comparison

Present majority, TF-IDF, and MiniLM validation metrics; then per-class F1 and
recall. Emphasize that the largest practical difference is class balance, not
the small accuracy delta.

### 6.3 Calibration

Present September/October roles, temperature, before/after NLL, Brier, ECE, and
confidence gap. Note class-level gaps that did not uniformly improve.

### 6.4 Operational benchmark

Present the fixed single-device CPU comparison as a bounded feasibility result.
Do not extrapolate to service throughput or cost.

### 6.5 Abstention and negative release result

Present the risk/coverage curve and gate failures. Explain thresholds 0.75 and
0.80 as diagnostic cases. The section ends with no eligible threshold and
`manual_review_only`.

### 6.6 Repository QA outcome

Summarize 13 findings, remediation themes, and the independently checked
evidence snapshot. Keep engineering assurance distinct from model validity.

### 6.7 Decision impact and causal evidence gap

Distinguish the observed no-go decision from unmeasured reviewer, timing, and
consumer effects. Answer RQ5 at the protocol level.

## 7. Discussion

1. Accuracy was a weak guide because the majority reference already appeared
   strong on that metric.
2. MiniLM improved observed class balance but did not solve the rare-class problem.
3. Better aggregate calibration did not guarantee a viable class-complete
   abstention policy.
4. A negative deployment decision is a substantive result, not project failure.
5. Software and governance controls changed the confidence appropriate for the
   evidence, not the underlying metric values.
6. Operational impact requires prospective randomized workflow evidence; model
   validation cannot supply the causal effect.

Compare these interpretations with the related-work sources without claiming
causal mechanisms not measured here.

## 8. Threats to validity and limitations

Cover source selection, label validity, English filtering, exact versus semantic
duplicates, temporal/taxonomy shift, validation reuse, class imbalance,
truncation, single-device benchmarking, calibration estimator limitations,
unmeasured demographic fairness, no reviewer study, no production system, no
energy measurement, and no frozen-test estimate.
Also cover the proposed trial's untested assumptions, unknown power inputs,
interference risk, and outcome-adjudication requirements.

## 9. Ethics, privacy, and human oversight

Explain data minimization, local retention, no narrative examples, prohibited
uses, automation bias risk, reviewer authority, and why human review is a
required but unevaluated safeguard.

## 10. Conclusion

Answer each research question directly, including RQ5's proposed estimands and
not-conducted status. End with the evidence-bounded result:
the compact transformer was the stronger validation candidate, but the fixed
class-aware policy rejected every threshold, leaving the system manual-only.

## 11. Reproducibility and artifact statement

List public source code, aggregate JSON, schemas, exact dependency locks, CI,
and QA evidence. State why raw narratives, database volume, model weights, and
calibrator remain local and are scheduled for deletion.

## Appendices

- A. Exact taxonomy and split counts.
- B. Model hyperparameters and selection rules.
- C. Full per-class validation metrics.
- D. Calibration definitions and reliability-bin tables.
- E. Complete abstention gate matrix and Wilson intervals.
- F. QA finding-to-control traceability.
- G. Claim checklist and evidence hashes.
- H. Prospective target-trial and causal estimand protocol.
