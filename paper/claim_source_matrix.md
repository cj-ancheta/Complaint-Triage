# Claim-to-source matrix

Status: publication claim audit complete on 2026-07-26

`Primary` means an original paper, official source, or standard. `Synthesis`
means the statement is this paper's evidence-bounded interpretation and must be
supported by project artifacts rather than made to look like a literature fact.

| ID | Planned manuscript claim | Source IDs | Type | Section | Scope caveat |
|---|---|---|---|---|---|
| C01 | The CFPB publishes eligible complaints only after specified process steps; narratives require consent and scrubbing. | CFPB-DB, CFPB-SHARE | Primary official | 4.1 | Describes the public source, not perfect de-identification. |
| C02 | Published complaints are not a statistical sample and complaint volume alone is not a prevalence estimate. | CFPB-DB | Primary official | 2, 4.1, 8 | Does not quantify selection bias in this cohort. |
| C03 | Product and issue taxonomies can change over time, making the observed label system operational rather than natural ground truth. | CFPB-DB | Primary official + synthesis | 4.1, 8 | The project's stability report supplies the window-specific evidence. |
| C04 | Other CFPB studies use predictive modelling, but their targets and protocols differ. | VAISHNAV-2024, JAIN-2026 | Primary studies | 3.1 | No cross-paper metric comparison. |
| C05 | A recent complaint classifier compared TF-IDF models with a transformer after balancing and collapsing the task. | JAIN-2026 | Primary study | 3.1 | Its bilingual synthetic augmentation, five classes, and random split prevent score comparison. |
| C06 | Term weighting and regularized linear text models form a meaningful classical reference. | SALTON-1988, GENKIN-2007 | Primary studies | 3.2, 5.2 | Does not claim TF-IDF/logistic regression is universally strongest. |
| C07 | MiniLM was designed to compress pretrained transformers through self-attention distillation. | MINILM-2020 | Primary preprint | 3.2, 5.3 | Original benchmark results do not transfer to complaints. |
| C08 | Classification measures encode different sensitivities to confusion-matrix and label-distribution changes. | SOKOLOVA-2009 | Primary study | 2, 5.1 | Does not remove the need for task-specific metric choices. |
| C09 | Macro-F1 must be defined explicitly because two non-equivalent computations circulate under that name. | OPITZ-2021 | Primary preprint | 5.1 | The project uses the mean of per-class F1 values. |
| C10 | Near-duplicate train-test overlap can inflate observed document-classification performance. | LARSON-2023 | Primary empirical | 4.3, 8 | Different document domain; exact complaint fingerprinting catches only exact normalized duplicates. |
| C11 | Temporal change is a genuine concern in NLP evaluation and motivates time-indexed splits. | MARGATINA-2023 | Primary empirical | 3.2, 4.3, 8 | Does not demonstrate measured drift in this project. |
| C12 | Proper scoring rules assess probability forecasts, whereas accuracy alone evaluates hard decisions. | BRIER-1950, GNEITING-2007 | Foundational | 3.3, 5.4 | Define the project's multiclass Brier convention. |
| C13 | Temperature scaling is a one-parameter post-hoc calibration method with strong empirical results in prior work. | GUO-2017 | Primary empirical | 3.3, 5.4 | No universal or future-period guarantee. |
| C14 | ECE is estimator-dependent; binning, norm, class conditioning, and which probabilities are measured can change conclusions. | NIXON-2019 | Primary empirical | 3.3, 5.4, 8 | The project therefore reports declared ECE variants plus proper scores. |
| C15 | Confidence calibration is weaker than full multiclass or classwise calibration, and a scalar temperature cannot act differently by class. | KULL-2019 | Primary empirical/method | 3.3, 6.3 | Does not prove a different calibrator would pass the release policy. |
| C16 | Selective classification trades coverage for predictive risk through rejection. | EL-YANIV-2010, GEIFMAN-2017 | Foundational/method | 3.3, 5.5 | The project's class-aware gates are governance constraints added to this framework. |
| C17 | Wilson score intervals characterize binomial proportion uncertainty under their assumptions. | WILSON-1927 | Foundational | 5.5 | They do not cover shift, dependence, label error, or harm. |
| C18 | Human presence alone does not neutralize automation risk; over-reliance can create monitoring and decision bias. | PARASURAMAN-1997 | Foundational synthesis | 3.4, 9 | No reviewer study was run, so effectiveness remains unknown. |
| C19 | Model cards should state intended use, evaluation context, and performance across relevant conditions. | MODEL-CARDS-2019 | Primary framework | 3.4, 5.6 | Documentation is evidence disclosure, not certification. |
| C20 | Dataset documentation should cover motivation, composition, collection, uses, and maintenance. | DATASHEETS-2021 | Primary framework | 3.4, 4, 5.6 | This repository uses an adapted data sheet. |
| C21 | AI risk management benefits from lifecycle governance, documented TEVV, defined human roles, and explicit go/no-go decisions. | NIST-AI-RMF-2023 | Official standard | 3.4, 5.6, 7, 9 | Voluntary framework; version 1.0 is under revision and is not certification. |
| C22 | The small accuracy delta, larger macro/worst-class gains, improved aggregate calibration, and failed class-aware abstention gates jointly support a stronger research candidate but no automation. | Project aggregate JSON and accepted QA snapshot | Synthesis | 6, 7, 10 | Internal validation-only conclusion; no frozen-test, deployment, or causal claim. |
| C23 | Resolving repository controls increases the confidence appropriate for the evidence without changing the model's empirical scores. | Accepted QA snapshot | Synthesis | 6.6, 7, 11 | QA cannot prove absence of all defects or bias. |
| C24 | Transparent prediction-model reporting requires explicit data, methods, evaluation, limitations, and intended-use information. | TRIPOD-AI-2024 | Primary consensus guidance | 2.5, 9 | Clinical guidance adapted for a non-clinical text-routing study; no formal compliance claim. |
| C25 | A causal question should be specified as a target experiment before attempting estimation from observational data. | HERNAN-2016 | Primary method | 4.7, 6.5, Appendix | The current cohort lacks treatment and reviewer outcomes and cannot emulate the proposed trial. |
| C26 | Prospective AI-intervention protocols and reports should specify intended use, human-AI interaction, input/output handling, and error analysis. | SPIRIT-AI-2020, CONSORT-AI-2020, DECIDE-AI-2022 | Primary consensus guidance | 2.5, 4.7, Appendix | Clinical reporting principles adapted to a non-clinical setting; the trial has not been conducted. |
| C27 | Human-AI effects depend on the interface, task, and users and therefore require direct prospective measurement. | CRESSWELL-2024, BRYNJOLFSSON-2025, PARASURAMAN-1997 | Primary experiments + foundational synthesis | 2.5, 6.5, Appendix | No effect size or direction is transported to complaint review. |
| C28 | The current evidence identifies a consequential no-go decision but no causal effect on reviewer accuracy, speed, consumer outcomes, or harm. | Project aggregate JSON, accepted QA snapshot | Synthesis | Abstract, 6.5, 7, 10 | Impact is decision impact; operational causal impact remains unestimated. |
| C29 | A future success rule must combine global benefit with prespecified route-specific safety constraints rather than reward an average that erases a required route. | HERNAN-2016, SPIRIT-AI-2020, Project abstention report | Primary method + synthesis | 4.7, 6.5, Appendix | Margins and power inputs must be stakeholder-defined before outcome access. |

## Coverage audit

- Data provenance and representativeness: C01-C03.
- Complaint-classification context: C04-C05.
- Classical and compact-transformer methods: C06-C07.
- Imbalanced metrics and evaluation design: C08-C11.
- Calibration and selective classification: C12-C17.
- Human oversight and evidence governance: C18-C21.
- Prediction reporting and causal design: C24-C27.
- Project-specific conclusions and impact boundary: C22-C23, C28-C29.

No row authorizes wording about statistical significance, demographic fairness,
production performance, frozen-test performance, observed causal effects, or
effective human review. The proposed causal estimands and trial are a prospective
design, not empirical findings.
