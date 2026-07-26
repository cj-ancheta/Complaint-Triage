# Verified reference set

Status: initial primary-source set complete on 2026-07-26

This is a working bibliography, not a list of endorsements. Each source has a
stable paper-local ID, a direct DOI or official URL, and a scope note that limits
how it may be used. The manuscript should cite the canonical publication page
where available. Preprints are identified explicitly.

## Complaint data and closely related studies

### CFPB-DB

Consumer Financial Protection Bureau. *Consumer Complaint Database*. Official
database documentation, updated 2025.
[Official page](https://www.consumerfinance.gov/data-research/consumer-complaints/)

Use for publication timing, narrative consent and scrubbing, taxonomy changes,
and the explicit warning that complaints are not a statistical sample. It does
not validate this project's derived population, labels, or metrics.

### CFPB-SHARE

Consumer Financial Protection Bureau. *How we share complaint data*. Official
field and privacy documentation, updated 2025.
[Official page](https://www.consumerfinance.gov/complaint/data-use/)

Use for fields published, narrative consent, and the Bureau's personal-data
scrubbing process. Public availability does not eliminate downstream privacy or
data-minimization duties.

### JAIN-2026

Jain, P., Tripathi, S., Garg, T., et al. "An intelligent transformer based
framework for bilingual financial complaint classification." *Scientific
Reports* 16, 20594 (2026).
[DOI](https://doi.org/10.1038/s41598-026-51771-w)

Direct complaint-classification comparison using TF-IDF models and a
transformer. Its balanced, five-category, translated bilingual corpus and random
80:20 split differ materially from this project's English-only, naturally
imbalanced, eleven-class temporal design; reported scores are not comparable.

### VAISHNAV-2024

Vaishnav, D., Neethinayagam, M., Khaire, A., and Woo, J. "Predictive Analysis
of CFPB Consumer Complaints Using Machine Learning." arXiv:2407.06399 (2024).
[Preprint](https://arxiv.org/abs/2407.06399)

Use only to establish that CFPB complaint data have supported other predictive
tasks, including response outcomes and topic modelling. It does not study this
project's product-routing target or validation protocol.

## Text representation, classification, and evaluation

### SALTON-1988

Salton, G., and Buckley, C. "Term-weighting approaches in automatic text
retrieval." *Information Processing & Management* 24(5), 513-523 (1988).
[DOI](https://doi.org/10.1016/0306-4573(88)90021-0)

Foundational support for term weighting as a reproducible single-term text
representation. It predates modern text classification and does not establish
that this project's TF-IDF configuration is optimal.

### GENKIN-2007

Genkin, A., Lewis, D. D., and Madigan, D. "Large-Scale Bayesian Logistic
Regression for Text Categorization." *Technometrics* 49(3), 291-304 (2007).
[DOI](https://doi.org/10.1198/004017007000000245)

Direct empirical support for regularized logistic models on high-dimensional
text. The Bayesian sparse method is not the same estimator used here.

### MINILM-2020

Wang, W., Wei, F., Dong, L., Bao, H., Yang, N., and Zhou, M. "MiniLM: Deep
Self-Attention Distillation for Task-Agnostic Compression of Pre-Trained
Transformers." arXiv:2002.10957 (2020).
[Preprint](https://arxiv.org/abs/2002.10957)

Original source for MiniLM's self-attention distillation and compact-model
motivation. Its benchmark results do not transfer to CFPB complaints.

### SOKOLOVA-2009

Sokolova, M., and Lapalme, G. "A systematic analysis of performance measures
for classification tasks." *Information Processing & Management* 45(4),
427-437 (2009).
[DOI](https://doi.org/10.1016/j.ipm.2009.03.002)

Supports metric definitions and the fact that measures respond differently to
label-distribution changes. It does not prescribe one universal primary metric.

### OPITZ-2021

Opitz, J., and Burst, S. "Macro F1 and Macro F1." arXiv:1911.03347, version 3
(2021).
[Preprint](https://arxiv.org/abs/1911.03347)

Supports explicit definition of macro-F1 because two non-equivalent formulas
are used in practice. It does not make macro-F1 sufficient on its own.

### LARSON-2023

Larson, S., Lim, G., and Leach, K. "On Evaluation of Document Classification
with RVL-CDIP." *EACL 2023*, 2665-2678.
[DOI](https://doi.org/10.18653/v1/2023.eacl-main.195)

Direct empirical evidence that near-duplicate train-test overlap can inflate a
document-classification benchmark. It studies document images/templates rather
than complaint narratives, so it motivates rather than validates our exact
fingerprinting rule.

### MARGATINA-2023

Margatina, K., Wang, S., Vyas, Y., John, N. A., Benajiba, Y., and Ballesteros,
M. "Dynamic Benchmarking of Masked Language Models on Temporal Concept Drift
with Multiple Views." *EACL 2023*, 2881-2898.
[DOI](https://doi.org/10.18653/v1/2023.eacl-main.211)

Establishes temporal change as an NLP evaluation concern and demonstrates
time-indexed benchmarking. Its masked-language-model factual probes are not
evidence of drift in this complaint cohort.

## Probabilities, calibration, and selective classification

### BRIER-1950

Brier, G. W. "Verification of Forecasts Expressed in Terms of Probability."
*Monthly Weather Review* 78(1), 1-3 (1950).
[DOI](https://doi.org/10.1175/1520-0493(1950)078%3C0001:VOFEIT%3E2.0.CO;2)

Original probability-forecast scoring source. State the multiclass convention
used by this project rather than assuming all Brier-score normalizations match.

### GNEITING-2007

Gneiting, T., and Raftery, A. E. "Strictly Proper Scoring Rules, Prediction,
and Estimation." *Journal of the American Statistical Association* 102(477),
359-378 (2007).
[DOI](https://doi.org/10.1198/016214506000001437)

Supports the role of proper scoring rules in probabilistic evaluation. It does
not make any one score a complete calibration diagnostic.

### GUO-2017

Guo, C., Pleiss, G., Sun, Y., and Weinberger, K. Q. "On Calibration of Modern
Neural Networks." *ICML 2017*, PMLR 70, 1321-1330.
[PMLR](https://proceedings.mlr.press/v70/guo17a.html)

Original modern temperature-scaling reference. It shows broad empirical
effectiveness, not a guarantee of classwise or future-period calibration.

### NIXON-2019

Nixon, J., Dusenberry, M., Jerfel, G., Nguyen, T., Liu, J., Zhang, L., and Tran,
D. "Measuring Calibration in Deep Learning." arXiv:1904.01685 (2019).
[Preprint](https://arxiv.org/abs/1904.01685)

Supports caution that ECE conclusions depend on binning, norm, confidence-only
versus all-probability measurement, and class conditioning.

### KULL-2019

Kull, M., Perello-Nieto, M., Kängsepp, M., Silva Filho, T., Song, H., and
Flach, P. "Beyond temperature scaling: Obtaining well-calibrated multi-class
probabilities with Dirichlet calibration." *NeurIPS 2019*.
[Proceedings](https://proceedings.neurips.cc/paper/2019/hash/8ca01ea920679a0fe3728441494041b9-Abstract.html)

Supports the distinction among multiclass, classwise, and confidence
calibration, including the limits of a single temperature parameter.

### EL-YANIV-2010

El-Yaniv, R., and Wiener, Y. "On the Foundations of Noise-free Selective
Classification." *Journal of Machine Learning Research* 11(53), 1605-1641
(2010).
[JMLR](https://www.jmlr.org/papers/v11/el-yaniv10a.html)

Defines selective classification and the risk-coverage trade-off. Its
noise-free theoretical setting does not establish this project's eligibility
gates or operational safety.

### GEIFMAN-2017

Geifman, Y., and El-Yaniv, R. "Selective Classification for Deep Neural
Networks." *NeurIPS 2017*.
[Proceedings](https://proceedings.neurips.cc/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html)

Direct method source for confidence-based rejection on a pretrained neural
classifier. Its probabilistic risk guarantee is not claimed by this project.

### WILSON-1927

Wilson, E. B. "Probable Inference, the Law of Succession, and Statistical
Inference." *Journal of the American Statistical Association* 22(158), 209-212
(1927).
[DOI](https://doi.org/10.1080/01621459.1927.10502953)

Original source for the score interval used in selective-precision gates. The
interval addresses binomial sampling uncertainty, not distribution shift,
label error, dependence, or policy harms.

## Human oversight, documentation, and assurance

### PARASURAMAN-1997

Parasuraman, R., and Riley, V. "Humans and Automation: Use, Misuse, Disuse,
Abuse." *Human Factors* 39(2), 230-253 (1997).
[DOI](https://doi.org/10.1518/001872097778543886)

Foundational synthesis linking over-reliance on automation to monitoring and
decision bias. It does not measure reviewer behavior in this project.

### MODEL-CARDS-2019

Mitchell, M., Wu, S., Zaldivar, A., et al. "Model Cards for Model Reporting."
*FAT\* 2019*, 220-229.
[DOI](https://doi.org/10.1145/3287560.3287596)

Supports intended-use, evaluation-context, and disaggregated model reporting.
A model card documents evidence; it does not itself make a model trustworthy.

### DATASHEETS-2021

Gebru, T., Morgenstern, J., Vecchione, B., et al. "Datasheets for Datasets."
*Communications of the ACM* 64(12), 86-92 (2021).
[DOI](https://doi.org/10.1145/3458723)

Supports structured documentation of dataset motivation, composition,
collection, use, and maintenance. This project adapts rather than reproduces
the full questionnaire.

### NIST-AI-RMF-2023

Tabassi, E. *Artificial Intelligence Risk Management Framework (AI RMF 1.0)*.
NIST AI 100-1 (2023).
[DOI](https://doi.org/10.6028/NIST.AI.100-1)

Official, voluntary risk-management framework supporting lifecycle governance,
documented test/evaluation/verification/validation, defined human roles, and
explicit go/no-go decisions. It is not a certification and is currently under
revision; the manuscript cites version 1.0 only.
