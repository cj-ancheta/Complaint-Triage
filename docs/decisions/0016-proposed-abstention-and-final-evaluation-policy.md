# ADR 0016: Proposed abstention and final-evaluation policy

- Status: Accepted
- Date: 2026-07-25
- Decision owner: Charles Jr Ancheta
- Scope: Phase 4 validation-only threshold selection and later locked test evaluation

## Context

CT-306 selects calibrated MiniLM as the operational candidate. The model returns
one normalized eleven-class probability distribution after applying the accepted
temperature `1.041049944456901`. That decision does not authorize treating every
top probability as a routing suggestion.

The system is decision support for a human complaint reviewer. A wrong suggestion
can delay routing or anchor the reviewer toward the wrong product team, while an
abstention consumes manual-review capacity. The first policy must therefore make
the accuracy-versus-coverage trade-off explicit rather than choosing a threshold
because its chart looks attractive.

The accepted validation period contains September and October 2024. September
was used to fit the temperature. October contains 41,831 rows and was used to
assess calibration. All validation rows were also involved in selecting the
MiniLM epoch. Threshold results are therefore tuning evidence, not an unbiased
estimate of future performance.

The frozen test partition contains 85,786 rows from November and December 2024.
It remains inaccessible until a threshold is selected, reviewed, accepted, and
committed.

## Decision supported

For each valid narrative, the model produces a top label and calibrated top-label
confidence.

```text
if confidence >= accepted_threshold:
    decision = "suggest"
    predicted_product = top_label
else:
    decision = "abstain"
    predicted_product = null
```

Equality is included in the suggestion branch. An abstention is a controlled
manual-review outcome, not an error. A suggestion remains advisory: the human
reviewer can accept, correct, or escalate it.

This policy does not cover malformed input, unavailable model or taxonomy,
detected drift, or a reviewer-identified multi-product case. Those conditions
always require manual review independently of confidence.

## Fixed threshold-analysis population

Use only the accepted October calibration-evaluation partition:

```text
2024-10-01 <= date_received < 2024-11-01
split_assignment = validation
record_count = 41,831
```

Require the accepted run ID, split version, population version, taxonomy,
ordered labels, model artifact, calibrator artifact, and source-report hashes.
The command must reproduce the accepted October prediction and calibration
aggregates before evaluating thresholds.

Do not query September or test. Keep narratives, identities, dates, logits,
probabilities, predictions, confidence values, and per-row threshold outcomes in
memory only.

## Fixed candidate thresholds

Evaluate exactly these top-label confidence thresholds:

```text
0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95
```

Also report `0.00` as the no-abstention reference, but it is not an eligible
policy candidate. Do not add a threshold, search unique confidence values, fit a
threshold optimizer, or change the grid after seeing results.

## Metric definitions

For `N` evaluated rows and threshold `t`:

```text
suggested_t = count(confidence >= t)
correct_suggested_t = count(confidence >= t and prediction = label)
incorrect_suggested_t = suggested_t - correct_suggested_t

coverage_t = suggested_t / N
review_rate_t = 1 - coverage_t
selective_accuracy_t = correct_suggested_t / suggested_t
selective_risk_t = 1 - selective_accuracy_t
false_suggestion_rate_t = incorrect_suggested_t / N
correct_suggestion_rate_t = correct_suggested_t / N
```

If no rows are suggested, selective accuracy and selective risk are null and the
candidate is ineligible.

For each actual class, report support, suggested count, coverage, correctly
suggested count, and accuracy conditional on being suggested. For each predicted
class, report suggestion count and precision. These are operational class slices,
not demographic fairness evidence.

Also report:

- macro and worst actual-class coverage;
- minimum predicted-class suggestion count;
- worst predicted-class precision;
- confusion matrix among suggested rows;
- review count and false-suggestion count; and
- Wilson 95% confidence intervals for global selective accuracy and each
  predicted-class precision as uncertainty diagnostics.

Use unrounded counts and ratios for every eligibility decision. Display rounding
must not change which candidate qualifies.

## Eligibility rule

A threshold is eligible only if all of these predeclared checks pass:

1. global selective accuracy is at least `0.93`;
2. global coverage is at least `0.60`;
3. false-suggestion rate is no greater than `0.05` of all cases;
4. every actual class has coverage of at least `0.10`;
5. every predicted class has at least `20` suggested cases; and
6. every predicted class has precision of at least `0.50`.

The global accuracy floor represents a material improvement over the accepted
no-abstention validation accuracy while recognizing that suggestions remain
human-reviewed. The coverage floor prevents a superficially accurate policy that
offloads most work. The false-suggestion cap expresses the error burden across
the complete queue. The class safeguards prevent aggregate performance from
silently eliminating a rare actual class or presenting a product suggestion that
is more often wrong than correct. The minimum suggestion count avoids declaring
a class precision gate passed on only a handful of examples.

Wilson intervals are reported but are not eligibility gates. Rare-class
uncertainty must remain visible in the model card and human-oversight policy.

## Selection rule

Among eligible candidates, select in this fixed order:

1. highest global coverage;
2. highest global selective accuracy;
3. lowest false-suggestion rate; and
4. lower threshold.

Because coverage decreases monotonically as the threshold rises, this normally
selects the lowest threshold that satisfies every safety and capacity gate. The
remaining criteria make tie handling explicit.

If no candidate is eligible, select no operational confidence threshold. The
system remains `manual_review_only`, and the report must identify every failed
gate by threshold. Do not weaken a requirement or introduce per-class thresholds
in response to failure. A different policy requires a new proposed ADR and owner
approval.

## Validation-only report

Write one closed aggregate report under
`data/evaluations/cfpb/abstention/`. It may contain only:

- source hashes and implementation commit;
- population and class counts;
- fixed thresholds and metric definitions;
- aggregate global and per-class threshold results;
- Wilson interval endpoints;
- eligibility checks and selection rationale;
- selected threshold or null;
- limitations and safe claims; and
- privacy and test-access declarations.

It must state:

```text
test_accessed = false
threshold_owner_approved = false
deployment_authorized = false
portfolio_promotion_approved = false
```

The implementation must be committed and clean before the real validation run.
Use atomic writes. An identical replay validates and returns the existing report
without inference. Changed source bytes, artifacts, calibration evidence,
population counts, predictions, or report identity fail closed.

## Threshold approval gate

The generated validation report may propose one threshold. It does not activate
that threshold. Charles must review and explicitly approve:

- the complete accuracy and coverage trade-off;
- every failed and passed gate;
- actual-class coverage and predicted-class precision;
- rare-class uncertainty;
- the manual-review workload; and
- the documented limitations.

Only after that approval may the ADR record the accepted threshold and the
repository advance to the locked final-test procedure.

## Locked final-test procedure

After the threshold is accepted and committed, a separate command may access the
frozen test partition exactly once as a new evidence run. It must require:

- a clean commit containing the accepted threshold and unchanged model,
  calibrator, taxonomy, and preprocessing;
- an exact operator confirmation such as `cfpb-final-test-v1`;
- the accepted validation threshold-report hash; and
- no option to override the threshold or test dates.

The test command reports both no-abstention and accepted-policy evidence:

- accuracy, macro F1, weighted F1, worst-class recall, top-2 accuracy, and
  confusion matrix;
- NLL, multiclass Brier, confidence gap, and both accepted ECE diagnostics;
- coverage, review rate, selective accuracy, false-suggestion rate, and correct
  suggestion rate;
- actual-class coverage and conditional accuracy;
- predicted-class suggestion count and precision; and
- the same operational narrative-length and month slices required by the
  specification.

The test report must be immutable and replayable without re-querying test. No
model, temperature, threshold, feature, taxonomy, or policy may change in
response to test results. If a result is disappointing, report it and decide
whether the project remains a demonstration; do not retune on test.

Final test access still does not authorize deployment or public metric
promotion. Those claims require separate review of the frozen report and
governance pack.

## Human-review policy carried forward

Manual review is mandatory when:

- confidence is below the accepted threshold;
- no threshold qualifies or has been approved;
- input validation fails;
- the active model, calibrator, or taxonomy is unavailable or mismatched;
- drift breaches a later approved alert boundary;
- the predicted class is outside the active taxonomy; or
- a reviewer identifies multiple products, ambiguity, or another reason to
  override the suggestion.

The interface must state that confidence is a calibrated model estimate, not a
probability that the complaint is truthful or that a business action is correct.
Abstained cases may still display model metadata for audit, but must not present a
predicted product as an approved route.

## Consequences and limitations

One global threshold is simple, reproducible, and easy to explain, but class
confidence distributions may differ. The class gates can reject an otherwise
strong global policy, which is intentional. A later class-specific policy would
need more parameters, stronger sample-size controls, and a new approval.

October has already influenced epoch selection and calibration assessment, so
the threshold analysis will be optimistic tuning evidence. Wilson intervals
describe sampling uncertainty only; they do not account for taxonomy drift,
distribution shift, label error, dependence among similar narratives, or future
reviewer behavior. The public database is not representative of all complaints.

Selective accuracy cannot measure reviewer productivity or downstream harm.
Before production, real stakeholders would need to price misroutes, review
capacity, escalation, service levels, and class-specific consequences.

## Approval

Charles approved the following Phase 4 boundary on 2026-07-25:

- the transition from Phase 3 to Phase 4;
- October validation as the threshold-selection population;
- the fixed threshold grid and metric definitions;
- the `0.93` accuracy, `0.60` coverage, `0.05` false-suggestion, `0.10`
  actual-class coverage, `20` predicted-class suggestion, and `0.50`
  predicted-class precision requirements;
- the ordered selection rule and `manual_review_only` fallback;
- the separate approval gate for the resulting threshold;
- the locked one-time test procedure after threshold acceptance; and
- the continued bans on deployment and public metric promotion.

This approval authorizes implementation and synthetic verification of the
validation-only threshold-analysis command. The implementation must still reach
a reviewed clean commit before it may run on the retained October validation
population. Any proposed threshold requires a separate explicit approval before
the frozen test procedure can begin.

## CT-401 evidence outcome

Charles accepted the CT-401 evidence and `manual_review_only` outcome on
2026-07-25. The analysis ran from clean implementation commit
`6866ee17242534d23a7dd1350092a420662b6c78` over all 41,831 expected October
validation records. It reproduced the accepted calibration evidence within the
fixed tolerance and left September and test untouched.

None of the ten candidate thresholds passed every approved gate. Threshold
`0.75` narrowly missed the false-suggestion ceiling and produced only four
suggestions for the least-suggested predicted class. Threshold `0.80` passed all
three global gates and every actual-class coverage gate, but one predicted class
received zero suggestions and therefore failed the predicted-class count and
precision requirements. The higher thresholds retained that class exclusion;
at `0.95`, global coverage and worst actual-class coverage also fell below their
floors.

The accepted report SHA-256 is
`73092c7fba0c069ba0d1a8b419e5203db3ffc8ed6f245000685b87e20e526716`.
The accepted fallback means no threshold exists for the separate approval gate,
so the locked final-test procedure is not authorized. Any attempt to introduce
class-specific thresholds, relax a gate, or evaluate a new grid requires a new
reviewed policy; it may not be inferred from these results or tuned on test.
