# When Aggregate Accuracy Is Not Enough

## A Governance-Aware Validation Study of Financial Complaint Triage

Charles Jr Ancheta

Portfolio research manuscript, validation-only draft

Evidence snapshot: `2d886756227787b2eed2d5f46754b2ab8fd7745b`

Draft date: 2026-07-26

> **Evidence boundary.** This manuscript reports internal validation and tuning
> evidence. It contains no frozen-test performance, does not authorize
> deployment or automated routing, and makes no demographic-fairness claim.

## Abstract

High aggregate accuracy can conceal weak behavior on rare classes in financial
complaint classification, while a high-confidence subset can appear useful even
when it excludes an operationally important route. This study evaluates that
problem as both a modelling and an evidence-governance question. We constructed
an eleven-class analytical cohort from public Consumer Financial Protection
Bureau complaint narratives received between September 2023 and December 2024.
The pipeline retained English narratives, removed conflicting-label duplicate
groups, kept the earliest record in same-label duplicate groups, and separated
training, validation, and a sealed later test partition chronologically. A
TF-IDF logistic-regression reference and a fully fine-tuned compact MiniLM
classifier were selected using the same 80,992-record validation population.
MiniLM's validation accuracy was 0.8859 compared with 0.8837 for TF-IDF, but the
more decision-relevant differences were macro F1 (0.7357 versus 0.6997) and
worst-class recall (0.2070 versus 0.0573). Scalar temperature scaling fitted on
September and assessed on October improved every declared aggregate probability
diagnostic without changing predicted labels. Nevertheless, no confidence
threshold from 0.50 to 0.95 satisfied the predeclared global and class-aware
abstention gates. At 0.80, aggregate selective accuracy reached 0.9450 while one
class received no suggestions, causing the policy to fail. An independent
repository QA exercise subsequently resolved thirteen findings and replayed the
aggregate evidence under protected continuous-integration controls. The study's
main result is therefore a bounded negative release decision: the compact
transformer was the stronger validation candidate, but neither aggregate
accuracy nor improved calibration justified automated routing. The accepted
outcome remains manual review only.

**Keywords:** consumer complaints; imbalanced text classification; MiniLM;
calibration; selective classification; human oversight; reproducible machine
learning

## 1. Introduction

Complaint triage is superficially a standard multiclass text-classification
task: accept a narrative and assign one product category. The operational
meaning is less simple. A wrong category may delay review, a majority class may
dominate conventional metrics, and a confident suggestion may encourage a
reviewer to accept an error. The relevant question is not only whether a model
predicts labels accurately. It is whether its performance is distributed across
classes, whether its confidence has a defensible empirical meaning, whether a
rejection policy preserves coverage for rare routes, and whether the evidence
can be reproduced without crossing privacy and evaluation boundaries.

The public CFPB database makes large-scale complaint research possible, but the
Bureau explicitly states that published complaints are not a statistical sample
of consumers' marketplace experiences. Narrative publication depends on
consumer consent and a publication process that includes steps to remove
personal information. Product and issue choices also reflect the form available
when a complaint was submitted and can change over time
[[CFPB-DB](references.md#cfpb-db); [CFPB-SHARE](references.md#cfpb-share)].
Consequently, the database is a record of an institutional process, not an
unbiased population survey or an independently adjudicated ground truth.

This study treats those limitations as part of the method. Only complaint
narratives are used as model features; company, geography, outcome, response,
and other potentially leaky or unnecessary fields are excluded. Exact
normalized duplicates are isolated before chronological splitting. The most
recent two months are sealed from modelling, while the preceding two months are
used for model selection, calibration, and abstention analysis. Results are
reported as internal validation evidence because repeated decisions on that
partition make a final-generalization interpretation inappropriate.

The study addresses four research questions:

1. **RQ1:** How do a TF-IDF logistic-regression reference and a compact MiniLM
   classifier compare under duplicate-isolated temporal validation?
2. **RQ2:** What changes when the selected transformer's probabilities are
   temperature-scaled and assessed on a later validation month?
3. **RQ3:** Can a fixed confidence-abstention policy satisfy both global utility
   and minimum per-class safeguards?
4. **RQ4:** Which repository controls are necessary before the evidence is
   credible enough for a portfolio research case study?

The contribution is deliberately narrower than a state-of-the-art claim. It is
a reproducible case study combining a strong classical reference, a compact
pretrained transformer, temporal and duplicate controls, multiclass calibration,
class-aware selective prediction, and software assurance. The negative release
outcome is part of the contribution: a threshold was not adopted merely because
its aggregate statistics looked attractive.

## 2. Related work

### 2.1 Consumer complaint classification

CFPB data have supported topic modelling, response-outcome prediction, and
complaint classification, but superficially similar studies can encode different
tasks. Vaishnav et al. used the database to predict response-related outcomes and
extract topics rather than the product route studied here
[[VAISHNAV-2024](references.md#vaishnav-2024)]. A recent bilingual complaint
classification study compared TF-IDF models with a multilingual transformer on
a balanced five-category corpus constructed with English-Hindi translation. It
used a random 80:20 split and reported stronger transformer accuracy
[[JAIN-2026](references.md#jain-2026)]. That work directly supports the relevance
of classical-versus-transformer comparison in this domain, but its balanced,
collapsed, translated task is materially different from the present naturally
imbalanced eleven-class, English-only temporal study. Its metric values are not
used as external baselines here.

### 2.2 Classical and compact pretrained text models

Term weighting provides a transparent single-term representation against which
more elaborate text representations can be compared
[[SALTON-1988](references.md#salton-1988)]. Regularized logistic models also have
a long empirical history in high-dimensional text categorization
[[GENKIN-2007](references.md#genkin-2007)]. These properties make TF-IDF plus
logistic regression a meaningful reference: it is not assumed to be weak, and
its sparse representation offers a materially different accuracy, footprint,
and complexity profile from a transformer.

MiniLM was introduced as a task-agnostic compression approach that distils
self-attention relationships from larger pretrained transformers
[[MINILM-2020](references.md#minilm-2020)]. The compact architecture is relevant
where a contextual model must later be assessed under bounded compute. The
original MiniLM benchmarks do not establish performance on complaint narratives;
the model therefore remains an empirical candidate rather than a presumed
winner.

### 2.3 Imbalance and evaluation design

Accuracy measures the proportion of correct hard predictions, but it weights
records rather than classes. In a severely imbalanced task, a classifier can
score well by serving the majority class while failing rare classes. Performance
measures have different invariance properties under changes to the confusion
matrix and label distribution, so metric selection must follow the task rather
than habit [[SOKOLOVA-2009](references.md#sokolova-2009)]. This study therefore
reports accuracy and weighted F1 for overall behavior, macro F1 for equal
per-class weighting, and worst-class recall as a direct guard against hiding the
least-served actual class. Macro F1 is defined as the arithmetic mean of the
eleven per-class F1 values because non-equivalent formulas circulate under the
same name [[OPITZ-2021](references.md#opitz-2021)].

Evaluation design also matters. An empirical review of the RVL-CDIP document
benchmark found substantial near-duplicate overlap between train and test data
and argued that such overlap can inflate observed performance
[[LARSON-2023](references.md#larson-2023)]. The document domain differs from
complaints, but the leakage mechanism motivates isolating repeated narratives.
Separately, temporal benchmarking research demonstrates that changing language
and facts can alter NLP evaluation over time
[[MARGATINA-2023](references.md#margatina-2023)]. A chronological split cannot
prove robustness to future shift, but it better represents the direction of the
intended inference than a random split over the entire observation window.

### 2.4 Calibration and selective classification

Hard-label accuracy does not evaluate the full predicted probability vector.
Proper scoring rules instead reward probability forecasts that assign coherent
probability to the event that occurs
[[BRIER-1950](references.md#brier-1950);
[GNEITING-2007](references.md#gneiting-2007)]. This study uses negative log
likelihood (NLL) and multiclass Brier loss alongside two expected calibration
error (ECE) summaries.

Temperature scaling learns one positive scalar applied to a model's logits
before softmax. Guo et al. found this simple post-hoc method effective across
several modern neural-network benchmarks
[[GUO-2017](references.md#guo-2017)]. Its simplicity is also a limitation. A
single temperature preserves the predicted class and acts identically across
class dimensions. Confidence calibration, classwise calibration, and full
multiclass calibration are distinct properties; a model may improve on a
top-label measure without becoming classwise calibrated
[[KULL-2019](references.md#kull-2019)]. ECE is itself estimator-dependent: bin
construction, norm, class conditioning, and the probabilities included can
change conclusions [[NIXON-2019](references.md#nixon-2019)]. We therefore avoid
the binary statement that a model is simply "calibrated."

Selective classification adds a reject option, trading coverage for predictive
risk [[EL-YANIV-2010](references.md#el-yaniv-2010)]. Confidence thresholds are a
common post-hoc mechanism for a pretrained neural classifier
[[GEIFMAN-2017](references.md#geifman-2017)]. Aggregate risk-coverage improvement
does not guarantee that each route remains represented, however. This study adds
minimum actual-class coverage, predicted-class suggestion count, predicted-class
precision, and Wilson lower-bound gates. Wilson intervals quantify binomial
proportion uncertainty under their assumptions; they do not address shift,
dependent observations, label error, or harm
[[WILSON-1927](references.md#wilson-1927)].

### 2.5 Human oversight and evidence governance

Manual review is not a magic remedy. Human-factors research identifies misuse
of automation, including over-reliance that can produce monitoring failures and
decision bias [[PARASURAMAN-1997](references.md#parasuraman-1997)]. A reviewer
study would be required to measure those effects here. Until then, human review
is a required safeguard with unknown effectiveness, not evidence that model
errors become harmless.

Documentation frameworks provide complementary transparency. Model cards call
for intended-use boundaries, evaluation context, and disaggregated performance
[[MODEL-CARDS-2019](references.md#model-cards-2019)], while datasheets call for
dataset motivation, composition, collection, use, and maintenance
[[DATASHEETS-2021](references.md#datasheets-2021)]. The NIST AI Risk Management
Framework 1.0 further emphasizes lifecycle governance, defined human roles,
documented testing/evaluation/verification/validation, and explicit go/no-go
decisions [[NIST-AI-RMF-2023](references.md#nist-ai-rmf-2023)]. These artifacts
improve traceability; none certifies a model as trustworthy.

## 3. Data and governance

### 3.1 Source and observation window

The source comprises sixteen complete monthly shards from the public CFPB
Consumer Complaint Database. Dates received span 2023-09-01 inclusive through
2025-01-01 exclusive. Acquisition occurred on 2026-07-22 using the official
public interface, with content-addressed source manifests and reconciliation
through raw, staging, analytical, and split layers.

The staging layer contained 979,995 records with complaint narratives. All
passed structural staging checks. The analytical policy retained 979,194 records
classified as English by Lingua 2.2.x and excluded 801 identified as
non-English. Language detection is a heuristic: short, multilingual,
code-switched, and named-entity-heavy narratives may be misclassified. Eligibility
does not imply that a narrative is representative, accurate, or harmless to
process.

Only narrative text is a model feature, and the CFPB product field is the
target. The identity-only taxonomy retains eleven current product labels without
merging rare categories into an "Other" class. Company, state, ZIP code, tags,
response outcome, timeliness, dispute fields, and other metadata are excluded to
reduce privacy exposure and prevent shortcuts unrelated to narrative-based
triage.

### 3.2 Duplicate isolation and temporal partition

Narratives are normalized using Unicode NFC, Unicode case folding, and collapsed
whitespace, then fingerprinted with SHA-256. A fingerprint group containing
conflicting product labels is excluded in full. For a same-label group, the
earliest record is retained and later repeats are excluded. This process leaves
561,342 canonical records and accounts for 417,852 duplicate-related
exclusions. The high exclusion count is treated as a substantive property of the
source, not hidden as generic cleaning loss.

The canonical cohort is divided chronologically:

| Partition | Inclusive start | Exclusive end | Records | Authorized use |
|---|---|---|---:|---|
| Train | 2023-09-01 | 2024-09-01 | 394,564 | Model fitting |
| Validation | 2024-09-01 | 2024-11-01 | 80,992 | Model, calibration, and threshold decisions |
| Frozen test | 2024-11-01 | 2025-01-01 | 85,786 | Sealed; no manuscript performance |

Exact normalized duplicates do not cross included partitions. The rule does not
detect paraphrases, templates with small differences, or semantic equivalence.
More aggressive matching could reduce leakage further but could also merge
distinct cases; no semantic-deduplication claim is made.

### 3.3 Class imbalance and retention

Training support ranges from 1,173 records for Debt or credit management to
248,062 for Credit reporting or other personal consumer reports. Validation
support ranges from 227 to 54,012. The rarest validation class therefore has
approximately 238 times fewer records than the majority class. This imbalance
motivates class-equal and worst-class measures and makes a class-complete
abstention policy materially harder than aggregate risk reduction.

Raw narratives and row-level derivatives remain local, are excluded from Git,
CI, cloud storage, and the public web application, and have a governed deletion
deadline of 2026-11-19 in Asia/Singapore. The repository retains aggregate
counts, metrics, hashes, schemas, and decision records. No narrative example,
complaint identifier, training vocabulary, or row-level prediction appears in
this manuscript.

## 4. Methods

### 4.1 Evaluation priorities

For class (k), precision is the fraction of predictions of (k) that are
correct, recall is the fraction of actual (k) records recovered, and F1 is
their harmonic mean. Macro F1 is the unweighted mean of the eleven class F1
values. Weighted F1 weights class F1 by validation support. Worst-class recall
is the minimum recall across the eleven actual classes. Model selection uses an
ordered rule: highest validation macro F1, then highest worst-class recall, then
highest weighted F1, followed by a simpler or earlier stable candidate where
applicable. No inferential significance test was predeclared, so observed
differences are not described as statistically significant.

A training-majority classifier provides a sanity reference. It always predicts
the most frequent training class and illustrates why accuracy alone is
misleading: its validation accuracy is 0.6669, while macro F1 is only 0.0727 and
ten classes have zero recall.

### 4.2 TF-IDF logistic-regression reference

The classical pipeline transforms narratives into a sparse TF-IDF representation
and fits regularized logistic regression. Candidate regularization values and
class-weight settings are evaluated only if optimization converges. The ordered
selection rule chooses candidate `c1p0-unweighted` on validation. The pipeline
and selected artifact are versioned; their reported metrics are read from the
committed aggregate evaluation rather than manually recomputed for this paper.

### 4.3 Compact MiniLM classifier

The neural candidate fully fine-tunes
`microsoft/MiniLM-L12-H384-uncased` at pinned revision
`9a201d7b3ebebc5feabf9fbb4b3a4ec5d3f2440d`. Inputs contain narrative text only
and are truncated at 384 model tokens. Training uses class-weighted loss, a
locally probed batch configuration, and a maximum of three completed epochs.
Epoch selection follows the same macro-F1, worst-class-recall, weighted-F1,
earlier-epoch order. Epoch 3 is selected. The run did not meet the configured
early-stopping condition before the three-epoch maximum.

### 4.4 Calibration design

After model selection, the validation period is divided by month. September
(39,161 records) fits one positive scalar temperature by minimizing NLL while
holding model weights fixed. October (41,831 records) assesses the fitted
temperature. Because dividing all logits by the same positive value does not
change their order, predicted classes and accuracy must remain constant; only
probabilities change.

Declared probability diagnostics are NLL, multiclass Brier loss, mean top-label
confidence, signed mean-confidence-minus-accuracy, 15-bin equal-width top-label
ECE, and 15-bin equal-mass top-label ECE. September results are in-sample
calibration-fit diagnostics. October is later-month validation tuning evidence,
not an independent final test. Class probability/prevalence gaps are reviewed
as limitations rather than summarized into a claim of full calibration.

### 4.5 Fixed abstention policy

The confidence policy evaluates thresholds from 0.50 through 0.95 in increments
of 0.05 on October. A record is suggested only when its calibrated maximum class
probability meets the threshold; otherwise it remains for manual review. Six
gates must all pass:

1. coverage at least 0.60;
2. selective accuracy at least 0.93;
3. false suggestion rate at most 0.05;
4. coverage of every actual class at least 0.10;
5. at least 20 suggestions for every predicted class; and
6. precision of every predicted class at least 0.50.

Wilson intervals accompany selective-precision estimates as uncertainty
diagnostics, but they are not substituted for the fixed point-estimate gates.

The policy and ordered threshold rule were committed before the real threshold
analysis. If no threshold passes, the predetermined fallback is
`manual_review_only`; the rule does not select the least-bad failing threshold.

### 4.6 Operational and repository assurance

An operational comparison uses a fixed batch of 512 October narratives repeated
three times on one Windows 11 laptop with an Intel Core Ultra 7 255HX. It records
load time, latency distribution, working set, and artifact footprint. This
bounded benchmark cannot be interpreted as service throughput, concurrency,
cloud cost, or an SLA.

Repository assurance uses exact platform-specific dependency locks with hashes,
separate standard and Linux CPU-transformer CI jobs, a PostgreSQL schema check,
strict typing on protected modules, coverage and warning ratchets, artifact
trust controls, secret/history scans, dependency audit, and branch protection.
An independent QA evidence pack replays aggregate artifacts by hash and schema
without reading narratives or complaint identifiers. Findings must be resolved
before owner acceptance of the paper-drafting snapshot.

## 5. Results

### 5.1 Model comparison

Table 2 presents the central validation comparison. Both learned models improve
substantially over the majority sanity reference. TF-IDF and MiniLM differ by
only 0.0022 accuracy points, but MiniLM's macro-F1 advantage is 0.0361 and its
worst-class-recall advantage is 0.1498. The larger class-equal and worst-class
differences answer RQ1 more meaningfully than the accuracy difference alone.

| Metric | Majority reference | TF-IDF | MiniLM | MiniLM - TF-IDF |
|---|---:|---:|---:|---:|
| Accuracy | 0.666881 | 0.883692 | 0.885853 | +0.002161 |
| Macro F1 | 0.072741 | 0.699661 | 0.735746 | +0.036085 |
| Weighted F1 | 0.533607 | 0.879291 | 0.886692 | +0.007401 |
| Worst-class recall | 0.000000 | 0.057269 | 0.207048 | +0.149779 |

MiniLM has higher observed per-class F1 for ten of eleven classes. TF-IDF
retains a small F1 lead for Mortgage: 0.8763 compared with 0.8736. The comparison
is therefore not a claim that one architecture dominates every class.

The rarest class, Debt or credit management, shows both improvement and a severe
remaining limitation. TF-IDF precision is 0.8125, recall 0.0573, and F1 0.1070
on 227 validation records. MiniLM precision is lower at 0.4196, while recall
rises to 0.2070 and F1 to 0.2773. In other words, the selected model recovers
more rare-class records at the cost of more false positives, and still misses
nearly four out of five actual records in that class. That trade-off is obscured
by the overall accuracy table.

Other observed recall gains are also concentrated outside the majority class.
For Payday loan, title loan, personal loan, or advance loan, MiniLM recall is
0.6298 compared with 0.4398 for TF-IDF. For Vehicle loan or lease it is 0.7801
compared with 0.6080. Conversely, majority-class recall falls from 0.9607 to
0.9328 while its precision rises from 0.9228 to 0.9523. These changes explain
why overall accuracy barely moves while class-balanced performance improves.

### 5.2 Calibration

The fitted temperature is 1.041049944456901. A value slightly above one softens
the predicted distribution. As required by the scalar transformation, September
and October predicted labels and accuracies are unchanged.

| October diagnostic | Before | After | Change |
|---|---:|---:|---:|
| Accuracy | 0.882121 | 0.882121 | 0.000000 |
| Mean top-label confidence | 0.905545 | 0.898805 | -0.006739 |
| Confidence minus accuracy | 0.023424 | 0.016685 | -0.006739 |
| Negative log likelihood | 0.371454 | 0.369804 | -0.001650 |
| Multiclass Brier loss | 0.177733 | 0.177053 | -0.000680 |
| Equal-width ECE, 15 bins | 0.023894 | 0.017336 | -0.006558 |
| Equal-mass ECE, 15 bins | 0.023598 | 0.017946 | -0.005652 |

Every declared aggregate October probability diagnostic improves in its intended
direction, answering the first part of RQ2. The conclusion remains deliberately
qualified. September selected the temperature and therefore gives in-sample fit
evidence. October is a later validation month, but both months belong to the
reused tuning partition. Moreover, several class-level probability/prevalence
gaps moved slightly in the wrong direction. The evidence supports "better on
the declared aggregate diagnostics," not "reliable probabilities for every
class."

### 5.3 Bounded operational comparison

The selected MiniLM plus calibrator occupies 133,481,428 bytes compared with
19,625,755 bytes for the TF-IDF artifact, a ratio of approximately 6.80. On the
fixed CPU workload, MiniLM's p50 latency is 48.2386 ms, p95 is 83.9696 ms, and
maximum observed latency is 111.1995 ms. Model load takes 4.1876 seconds, and
peak working set reaches 1,003,794,432 bytes. Under the project's predeclared
single-device feasibility rule, the calibrated MiniLM proceeds to abstention
analysis. This result does not authorize a service and cannot be extrapolated to
multi-user throughput or infrastructure cost.

### 5.4 Abstention and the negative release result

No threshold passes all six gates. Lower thresholds retain class coverage but
miss aggregate accuracy and false-suggestion requirements. Higher thresholds
improve aggregate selective accuracy while progressively removing rare predicted
classes. The transition is visible in two diagnostic thresholds:

| Threshold | Coverage | Review rate | Selective accuracy | False suggestion rate | Blocking evidence |
|---:|---:|---:|---:|---:|---|
| 0.75 | 0.856279 | 0.143721 | 0.936402 | 0.054457 | False suggestions exceed 0.05; least-suggested class has 4 cases |
| 0.80 | 0.825440 | 0.174560 | 0.945032 | 0.045373 | One predicted class has zero suggestions and cannot meet count or precision gates |

At 0.75, selective accuracy passes but the false-suggestion rate does not, and a
predicted class has too little evidence. At 0.80, the global accuracy and false-
suggestion gates pass, yet an entire predicted route disappears. Thresholds 0.85
and 0.90 retain the same minimum-count and predicted-class-precision failures.
At 0.95, coverage also falls below 0.60 and at least one actual class receives
less than 0.10 coverage. Thus the risk-coverage curve improves globally while
the class-completeness policy fails.

RQ3 is answered negatively: no tested confidence policy satisfies both global
utility and the predeclared per-class safeguards. The accepted operational
status is `manual_review_only`. No threshold is selected, no complaint may be
automatically routed or even surfaced with an authorized model suggestion, and
the frozen test remains sealed.

### 5.5 Repository QA outcome

The repository-wide QA assessment recorded thirteen findings: three high,
seven medium, and three low severity. Remediation addressed dependency and
supply-chain boundaries, offline CPU-transformer CI, branch protection,
coverage and warning ratchets, strict type-checking scope, database constraints,
data and serialization boundaries, and maintenance evidence. The accepted pack
contains 119 aggregate checks and reconciles all thirteen findings as resolved.

Required `standard`, `transformer-cpu`, and `security` jobs run in protected pull
requests. Administrators are subject to the policy; force pushes and branch
deletion are disabled; linear history and conversation resolution are required.
The evidence pack validates against JSON schemas and binds the accepted
paper-drafting state to commit
`2d886756227787b2eed2d5f46754b2ab8fd7745b`.

RQ4 is answered at the repository level: credible portfolio evidence required
not just model artifacts, but source and split lineage, aggregate schemas,
content hashes, locked environments, independent CPU execution, database and
privacy controls, a resolved finding register, and an explicit owner acceptance
record. These controls establish what was checked and reproducible; they do not
prove the absence of all defects, bias, or future regressions.

## 6. Discussion

### 6.1 Accuracy was a weak decision guide

The majority reference correctly labels roughly two thirds of validation records
while failing ten classes completely. That result makes the central warning
concrete: accuracy rewards the dominant record distribution, not minimum service
across routes. The learned models' 0.0022 accuracy difference could reasonably
be described as small, yet it coexists with a 0.0361 macro-F1 difference and a
0.1498 worst-recall difference. Architecture selection changes depending on
whether the objective is average record correctness or protection against a
rare-class collapse.

The findings do not make macro F1 a universal substitute. Macro F1 averages
class-level harmonic means and can still conceal whether a gain comes from
precision or recall. The rarest-class example demonstrates this: MiniLM improves
F1 chiefly through recall while sacrificing precision. Reporting the per-class
components and worst recall prevents a single macro statistic from becoming a
new aggregate blind spot.

### 6.2 A stronger candidate is not a releasable system

The compact transformer is the stronger validation candidate under the declared
quality order, and it passes a bounded operational feasibility comparison. Those
facts answer a research selection question, not a deployment question. The
system has no approved threshold, reviewer interface, monitoring loop, service
security assessment, override protocol, or measured workflow effect. Treating
candidate selection as deployment authorization would collapse distinct
evidence gates into one performance number.

This distinction is particularly important for portfolio work. A polished app
can make a research artifact look operationally mature. The accompanying public
interface must therefore present aggregate evidence and a simulated workflow
only; it must not accept real complaints, expose model artifacts, or imply that
the classifier is available for routing.

### 6.3 Aggregate calibration did not produce a class-complete policy

Temperature scaling improves NLL, Brier loss, both ECE variants, and the mean
confidence gap on October. The improvements are internally consistent and not
merely an artifact of one ECE binning scheme. Still, a single temperature cannot
correct classes differently, and class-level gaps do not improve uniformly.

The abstention analysis exposes the operational consequence. If only aggregate
selective accuracy and false-suggestion rate were considered, 0.80 would look
attractive: it retains 82.5% of records and reaches 94.5% selective accuracy.
The class-aware view shows that one predicted category receives no suggestions.
For a triage system, silently deleting a route from the suggestion vocabulary is
not equivalent to safe uncertainty handling. The negative policy decision is
therefore more informative than an optimized global threshold would have been.

### 6.4 Governance changed the strength of the claim

QA remediation did not alter the reported model metrics. It altered the
confidence appropriate for their provenance. Exact dependency locks reduce
environment ambiguity; protected CPU execution tests whether the compact model
actually runs outside its training machine; schemas prevent quiet changes to
aggregate evidence; content hashes bind decisions to artifacts; privacy checks
constrain what enters the repository; and branch protection makes required
checks harder to bypass.

These controls also make negative results durable. Without a versioned policy,
a later author could choose 0.80 after seeing the curve and quietly relax the
missing-class constraint. Here, the failed gate, null selected threshold, and
manual-only fallback are committed evidence. Governance is therefore part of
the empirical method, not an appendix added after a favorable result.

## 7. Threats to validity and limitations

### 7.1 Construct and source validity

CFPB product labels are consumer- and process-facing taxonomy selections, not
independent expert adjudications of a narrative's single true category. Some
narratives may reasonably concern multiple products. Publication depends on
complaint intake, company-response processes, consumer consent for narratives,
and the Bureau's publication criteria. The resulting cohort is neither a sample
of all consumers nor a prevalence measure of financial harm.

English-language filtering may exclude valid multilingual complaints or retain
misclassified text. Restricting features to narratives improves data
minimization and evaluates the intended text signal, but it may omit structured
information a real reviewer legitimately uses. Conversely, adding company,
geography, or outcome fields could introduce privacy, representation, or target
leakage problems.

### 7.2 Internal and temporal validity

Exact fingerprinting removes normalized exact repeats but not paraphrases or
near-duplicate templates. Residual overlap may remain, while a more aggressive
method could falsely merge distinct complaints. The chronological design is
closer to prospective use than a random split, but one observation window cannot
establish stability under later language, product, intake, or taxonomy change.

Validation was reused for epoch selection, model comparison, temperature
assessment, operational candidate selection, and threshold analysis. Reported
values are therefore optimistic tuning evidence. The sealed November-December
partition has no manuscript performance estimate, and no final-generalization
claim is available. This is an intentional cost of refusing to open the test
after the release policy failed.

### 7.3 Measurement validity

Macro F1 and worst-class recall make imbalance visible but do not quantify the
business cost of each error. The rarest class has only 227 validation records,
so its estimates are less stable than majority-class estimates. Wilson intervals
address one form of sampling uncertainty for proportions but not temporal shift,
duplicate dependence, label error, or downstream harm. No paired inferential
test or confidence interval for model-to-model metric differences was
predeclared.

ECE is a binned summary and depends on estimator choices. NLL and Brier loss add
proper-score views, but no finite collection of aggregate diagnostics proves
full multiclass calibration. The fixed threshold grid is deliberately limited;
the failure of this policy does not prove that every conceivable selective
classifier or class-specific policy must fail. Proposing a new policy would
require a new precommitted study without using the frozen test.

### 7.4 External and operational validity

The MiniLM input limit truncates narratives beyond 384 model tokens and may omit
material context. The CPU benchmark uses one device, one fixed workload, and
three repetitions. It provides no evidence about concurrency, uptime, cloud
cost, energy use, carbon emissions, or service-level performance. Training used
a local CUDA environment; total measured training-plus-validation time across
three epochs was approximately 5,292.7 seconds, but energy was not measured.

No model is deployed. There is no evidence about reviewer accuracy,
productivity, time savings, override behavior, appeal, downstream resolution,
consumer harm, or organizational incentives. Human oversight is a design
requirement whose real effectiveness remains untested.

## 8. Ethics, privacy, and human oversight

The application domain involves narratives about financial difficulties and may
contain sensitive circumstances even after source scrubbing. Data minimization
therefore governs both features and publication: the model sees only narratives,
while public evidence contains no narrative fragment, identifier, vocabulary,
row-level prediction, local explanation, or screenshot of governed data. Raw
and derived text remains local under a deletion deadline.

The classifier must not determine truth, liability, compensation,
creditworthiness, vulnerability, fraud, company misconduct, or complaint
priority. Confidence is the model's score for its product label, not the
probability that a consumer is truthful or deserves a particular outcome.
Attention weights and post-hoc token attributions are not authorized as causal
reasons or business justifications.

No protected attributes were collected for modelling or evaluated. Month,
narrative length, class rarity, and product slices are operational diagnostics,
not demographic groups. The study therefore cannot claim demographic fairness
or equal impact. Public complaint data may reflect unequal access, awareness,
reporting practices, institutional processes, and historical inequities that
are not observable in the selected fields.

If a later study presents suggestions to reviewers, reviewers must retain the
authority to correct, decline, and escalate them. The interface would need to
make uncertainty and the manual fallback salient, log overrides without turning
them into punitive surveillance, and test for over-reliance as well as time
savings. Until that human-subject and workflow evidence exists, the present
manual-only decision is the least expansive claim consistent with the results.

## 9. Reproducibility and artifact statement

The public repository contains source code, migrations, contracts, aggregate
manifests, evaluation JSON, decision records, the dataset sheet, model card,
risk register, QA finding register, accepted QA snapshot, exact dependency
locks, and protected CI configuration. Aggregate files name the research run,
source artifacts, software versions, hashes, privacy fields, selection rules,
limitations, and reproduction commands. Tests validate JSON schemas, reconcile
counts and finding IDs, verify evidence paths, and enforce manuscript claim
boundaries.

Row-level reproduction is intentionally time-limited. Raw complaints, the local
database volume, model weights, prediction arrays, calibrator, and any governed
text-bearing derivative are excluded from Git and scheduled for deletion. Their
absence from the public repository is a privacy and retention control, not an
oversight. The retained aggregate evidence supports audit of the reported
numbers but will not permit future researchers to reconstruct individual
narratives or rerun training after deletion.

The manuscript uses paper-local citation IDs linked to
[`references.md`](references.md). The exact claim-to-source relationship and
scope caveat for each external statement is recorded in
[`claim_source_matrix.md`](claim_source_matrix.md). Project-specific numerical
claims map to the accepted sources in
[`evidence_inventory.md`](evidence_inventory.md). Any publication-formatted
version should be generated from these records and rechecked for citation,
privacy, and prohibited-claim compliance.

## 10. Conclusion

RQ1 asked whether contextual modelling changed the result under
duplicate-isolated temporal validation. MiniLM was the stronger research
candidate: its accuracy advantage over TF-IDF was small, but its observed macro
F1 and worst-class recall were materially higher. It improved F1 in ten classes,
while TF-IDF retained the Mortgage lead and the rarest class remained weak.

RQ2 asked what temperature scaling changed. A temperature fitted on September
improved all declared aggregate October probability diagnostics and reduced
overconfidence without changing predicted labels. It did not establish uniform
classwise or future-period calibration.

RQ3 asked whether confidence-based abstention could meet both global and
class-aware safeguards. It could not. Thresholds that achieved attractive
selective accuracy either exceeded the false-suggestion boundary or lacked
adequate suggestions and precision for every class. No threshold qualified.

RQ4 asked what made the evidence credible enough for a portfolio research case
study. The answer included data and split lineage, predeclared decisions,
aggregate schemas and hashes, locked environments, independent CPU execution,
privacy controls, protected CI, a resolved finding register, and explicit owner
acceptance. These controls strengthen traceability without converting validation
results into final or production evidence.

The compact transformer is therefore selected only as a validation candidate.
The system is not authorized for automated routing, deployment, frozen-test
access, or public promotion of its metrics as final performance. The most
important result is not 88.6% accuracy. It is that an apparently useful 94.5%
selective-accuracy threshold failed because it stopped suggesting one of the
required routes. Aggregate performance was not allowed to erase the least-served
class; the accepted outcome remains manual review only.

## Declarations

**Data availability.** The source database is publicly available from the CFPB.
This repository publishes aggregate evidence only. Governed row-level data and
derived artifacts are local, non-redistributable project materials scheduled
for deletion.

**Code availability.** Source code, schemas, documentation, exact environment
locks, and aggregate evidence are available in the project repository.

**Conflicts of interest.** This is an independently developed portfolio research
project. No conflict is declared.

**Human participants.** No reviewer or consumer study was conducted. The work
analyses public administrative complaint records under a data-minimization and
no-redistribution policy.

**Funding.** No external funding is declared.
