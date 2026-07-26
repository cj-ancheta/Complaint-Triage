# Prospective causal evaluation protocol

Status: `design_blueprint_not_registered_not_conducted`

This appendix defines the experiment that would be required to estimate the
operational effect of AI-assisted complaint triage. It is not a report of a
trial, a deployment plan, or authorization to expose reviewers or consumers to
the model. The retrospective CFPB cohort contains neither treatment assignment
nor reviewer and downstream workflow outcomes, so it cannot identify these
causal effects.

## 1. Causal question

Among eligible complaint reviewers handling newly received complaints, what is
the effect of access to a governed model suggestion interface, compared with
the existing manual-only interface, on independently adjudicated routing
correctness and time to a final routing decision, without materially worsening
performance for any required product route?

The intended intervention is decision support, not autonomous routing. The
reviewer remains responsible for the final route and may ignore, correct, or
escalate every suggestion.

## 2. Target-trial specification

| Component | Prospective specification |
|---|---|
| Eligibility | Trained complaint reviewers who provide informed organizational consent; newly received complaints that meet a prespecified language and routing-taxonomy definition; exclude training cases, duplicate replays, appeals, and cases requiring emergency or specialist handling. |
| Unit of assignment | Reviewer, team, or reviewer-period cluster. Individual complaints should not be randomized within a reviewer if exposure can teach persistent model behavior and contaminate later control decisions. |
| Control strategy | Current manual-only interface with the same narrative, taxonomy, escalation path, and non-model resources available under ordinary practice. |
| Intervention strategy | The same interface plus a clearly labelled model suggestion, uncertainty presentation, manual fallback, and correction/escalation controls. No automatic submission and no suggestion for out-of-policy cases. |
| Assignment | Concealed random assignment, stratified by site/team and reviewer experience where feasible. Allocation occurs only after eligibility and before exposure. |
| Follow-up | From case opening to final route, with a prespecified window for adjudication, correction, escalation, and immediate downstream re-routing. Longer-term resolution outcomes require a separate protocol. |
| Co-primary outcomes | Independently adjudicated correct final route; active review time from case opening to final route. Queue waiting time is reported separately. |
| Safety outcomes | Route-specific error and omission, correction and escalation, suggestion acceptance when wrong, cases lacking an eligible suggestion, and severe process incidents defined before registration. |
| Causal contrasts | Intention-to-treat effect of assignment to the suggestion interface versus manual-only review; route-specific risk differences and time effects; per-protocol estimates only as secondary analyses with explicit assumptions. |
| Analysis | Cluster-aware estimation with prespecified covariate adjustment, confidence intervals, missingness rules, multiplicity handling, and route-specific non-inferiority constraints. |

This target-trial structure follows the discipline of stating the experiment
before considering causal estimation [[HERNAN-2016](references.md#hernan-2016)].
The protocol adapts human-AI intervention reporting principles from
SPIRIT-AI, CONSORT-AI, and DECIDE-AI while recognizing that those guidelines
were written for clinical settings
[[SPIRIT-AI-2020](references.md#spirit-ai-2020);
[CONSORT-AI-2020](references.md#consort-ai-2020);
[DECIDE-AI-2022](references.md#decide-ai-2022)].

## 3. Estimands

Let `A = 1` denote randomized access to the suggestion interface and `A = 0`
manual-only review. Let `Y(a)` be an indicator that the final route would be
correct under assignment `a`, and let `T(a)` be active review time under that
assignment.

The primary correctness estimand is the intention-to-treat risk difference:

`ATE_correct = E[Y(1) - Y(0)]`.

The primary time estimand is:

`ATE_time = E[T(1) - T(0)]`.

For each required route `r`, the safety estimand is:

`ATE_correct,r = E[Y(1) - Y(0) | independently adjudicated route = r]`.

The trial should not declare success from a favorable overall average alone.
Success requires both the prespecified global criterion and every route-specific
safety constraint. Non-inferiority margins, minimum important time difference,
and harm weights must be set by domain owners and reviewers before power
calculation or outcome access; this paper does not invent them after observing
validation performance.

## 4. Causal structure and identification

The manuscript's F7 DAG separates baseline variables, randomized assignment,
post-assignment behavior, and outcomes. Case complexity and true route can
affect model correctness, reviewer behavior, and review time. Reviewer
experience can affect use of the suggestion and both outcomes. Calendar period
can affect case mix and queue conditions. Stratified randomization blocks the
back-door paths from those baseline variables to assignment in expectation.

Suggestion visibility, acceptance, override, and escalation occur after
assignment. They are mediators, not baseline adjustment variables for the
intention-to-treat total effect. Conditioning on them in the primary analysis
would change the estimand and can introduce selection bias. Any mediation or
per-protocol analysis must be labelled secondary and state additional
assumptions.

Identification of the intention-to-treat effects requires consistency, no
unmeasured interference between randomized clusters, positivity, correct
outcome measurement, and adherence to the randomized assignment. Cluster
assignment reduces but cannot automatically eliminate spillovers, learning,
or shared-queue effects. These must be measured and discussed.

## 5. Intervention fidelity and human factors

Before randomization, the study must freeze the model identity, taxonomy,
calibrator, interface, eligible-suggestion policy, and fallback behavior. The
interface must state that a suggestion is fallible, preserve access to all
routes, require an affirmative reviewer action, and make correction and
escalation at least as easy as acceptance. Logging should capture exposure,
latency, acceptance, correction, escalation, and missing output without storing
unnecessary narrative copies.

Human presence is not itself a safeguard. Prior randomized and field studies
show that effects of AI assistance depend on presentation, task, and worker
characteristics; their results motivate direct measurement rather than effect
transport [[CRESSWELL-2024](references.md#cresswell-2024);
[BRYNJOLFSSON-2025](references.md#brynjolfsson-2025)]. Reviewers should receive
equivalent task training, but intervention-specific instruction must be
reported as part of the treatment.

## 6. Outcome measurement

Correctness must be determined by an adjudication process independent of study
assignment and model output. The adjudication rubric, number and qualifications
of adjudicators, disagreement resolution, blinding, and inter-rater agreement
must be prespecified. The consumer-selected database category is not assumed to
be perfect ground truth for the trial.

Active review time should exclude queue delay and unrelated interruptions using
a prespecified rule. Secondary outcomes may include total elapsed time,
correction rate, escalation rate, reviewer confidence, and severe error types.
Consumer resolution, financial harm, satisfaction, or institutional cost must
not be claimed unless directly and validly measured under a separately adequate
follow-up design.

## 7. Analysis and missing data

The primary analysis should estimate intention-to-treat effects with uncertainty
intervals that respect the unit of randomization. A prespecified generalized
linear or hierarchical model may improve precision using baseline route, case
complexity proxies, reviewer experience, site/team, and calendar block. The
protocol must define handling for abandoned cases, missing timestamps, model
failures, reviewer crossover, adjudication disagreement, and cluster attrition.

Report the full route-specific outcome table regardless of statistical
significance. If the trial is underpowered for a rare route, the result is
inconclusive rather than evidence of safety. Exploratory heterogeneity analyses
must be identified as such and should not substitute for the prespecified route
constraints.

## 8. Safety monitoring and stopping

An independent owner should review aggregate blinded quality and unblinded
safety results under a written charter. Stop or pause criteria should include a
severe process incident, evidence of systematic route omission, excessive wrong
suggestion acceptance, data leakage, model or taxonomy drift, interface failure,
or violation of allocation and consent controls. No adaptive threshold or model
change is allowed inside the confirmatory trial without treating the change as
a new intervention version.

## 9. Registration, power, and reporting

Before recruitment or outcome access, register the protocol, estimands,
allocation, sample-size calculation, margins, analysis code, outcome rubric,
stopping rules, and deviations policy in an appropriate public registry or
time-stamped repository. Calculate sample size from the chosen cluster design,
baseline event rates, intracluster correlation, attrition allowance, and
stakeholder-defined effect and safety margins. Validation-set accuracy is not a
substitute for these quantities.

Publish null and harmful results. A future trial report should disclose the
intervention version, intended use, human-AI interaction, errors, protocol
deviations, and code/access restrictions. The current manuscript supplies the
predictive precursor and negative release decision; it does not supply a causal
effect estimate.

## 10. Prerequisites for any trial

1. Independent editorial and ethics/privacy review of the study and interface.
2. A newly authorized model and suggestion policy evaluated without reusing the
   sealed test for tuning.
3. Stakeholder-defined harm taxonomy, route constraints, and meaningful effect
   sizes.
4. Independent outcome adjudication and a contamination-aware randomization
   plan.
5. Prospective registration, power analysis, monitoring charter, consent or
   organizational authorization, and incident response.
6. A separate deployment decision after the trial; trial completion does not
   automatically authorize production use.
