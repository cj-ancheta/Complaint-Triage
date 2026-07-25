# Human Oversight Policy

- Policy version: `1.0.0`
- Current status: all complaints require manual review
- Approved model threshold: none
- Automated routing: prohibited

## Purpose

Human oversight is a decision boundary, not a decorative confirmation button.
The model can supply research evidence, but a qualified reviewer remains
responsible for the product route, correction, escalation, and any downstream
action. Confidence is a model estimate for its product prediction; it is not a
truth score or business justification.

## Current operating rule

No threshold passed every ADR 0016 gate. Therefore the only accepted behavior is
`manual_review_only`. No complaint may be automatically routed, and the current
model suggestion must not be presented as an approved route in a public or
operational interface.

Offline aggregate analysis may continue within the approved retention and data
boundaries. Row-level demonstrations must use synthetic or curated non-sensitive
fixtures unless a separate public-input policy is approved.

## Review triggers

Manual review is mandatory when any of the following applies:

- no operational threshold exists or has not been explicitly approved;
- model confidence is below a future approved threshold;
- the input is missing, malformed, oversized, unsupported, non-English,
  ambiguous, or appears to contain multiple products;
- the model, tokenizer, calibrator, taxonomy, or evidence identity is missing or
  mismatched;
- a requested label is outside the active eleven-class taxonomy;
- a reviewer disagrees with the suggestion or detects contextual information the
  model may have missed;
- monitoring is unavailable, stale, incomplete, or beyond a warning/stop
  boundary;
- drift, incident, security, retention, or dependency controls are breached; or
- service health or audit logging is unavailable.

These triggers are independent: high confidence never overrides a validation,
security, drift, or reviewer escalation condition.

## Reviewer controls

A future authorized review interface must allow the reviewer to:

- inspect the complete complaint in the approved secure system;
- see the active model, taxonomy, calibration, and policy versions;
- distinguish a suggestion from a confirmed route;
- accept, correct, mark ambiguous/multiple-product, or escalate;
- select any valid taxonomy label rather than only the model's top choice;
- record a structured override or escalation reason without copying sensitive
  narrative text into analytics logs;
- defer a case and return to it without losing the original input or audit trail;
- report unsafe behavior or request immediate suspension; and
- continue manual work when the model service is unavailable.

The interface must not use preselected acceptance, misleading colors, false
certainty, urgency cues, or wording such as “AI-approved.” Explanations must be
described as model evidence, never causal or legal reasoning.

## Escalation

Escalate a case to an appropriate operations specialist when the correct product
is unclear, multiple products are material, taxonomy coverage is inadequate,
the complaint contains an urgent safety/legal issue under organizational policy,
or the reviewer lacks authority. The model must not determine escalation urgency.

Escalate the system to the model owner and suspend suggestions when errors cluster,
rare classes disappear, override rates change materially, taxonomy changes,
confidence shifts, monitoring fails, or an incident affects evidence integrity,
privacy, or security. Resume only through the promotion checklist.

## Override and audit records

A future service should record only what is needed for accountability:

- request/case reference managed by the authorized case system;
- model, tokenizer, calibrator, taxonomy, and threshold-policy versions;
- timestamp and service request ID;
- suggested class and confidence only if suggestions are authorized;
- reviewer action: accept, correct, ambiguous, escalate, or unavailable;
- final route when legitimately available; and
- a closed, non-sensitive reason code.

Do not place raw public-demo narratives, free-text override explanations, or
secrets in routine logs. Reviewer actions are not automatically ground truth and
must not flow directly into training without adjudication and a new data version.

## Responsibility boundaries

| Role | Responsibility | Must not do |
|---|---|---|
| Reviewer | Decide or escalate the product route using the full case and policy | Treat confidence as truth or defer responsibility to the model |
| Operations owner | Define routing procedures, staffing, escalation, service levels, and reviewer training | Change model/taxonomy policy without governance review |
| Model owner | Maintain evidence, versions, calibration, monitoring design, and stop recommendations | Activate a threshold or retune on frozen test without approval |
| Data steward | Enforce source, access, retention, deletion, and feedback-label quality | Repurpose narratives or extend retention silently |
| Security/service owner | Protect the API, secrets, logs, dependencies, availability, and incidents | Expose artifacts or raw text through unsafe diagnostics |
| Governance approver | Review intended use, risks, evidence, claims, and promotion decisions | Approve on aggregate accuracy alone |

Charles currently holds the project/model-owner role for this portfolio. No
operational organization, qualified reviewer group, or independent governance
approver has been appointed, which is another reason deployment is not
authorized.

## Training and review readiness

Before future reviewers use model suggestions, training must cover model scope,
taxonomy, confidence meaning, rare-class limitations, automation bias, privacy,
override/escalation, unavailable mode, and incident reporting. Readiness should
be tested with synthetic cases that include disagreement, ambiguity, model
failure, and high-confidence error—not only easy acceptance flows.

## Oversight effectiveness

If a service is later authorized, measure acceptance, correction, escalation,
unavailable-mode, and time-to-resolution patterns by valid operational slices.
Do not optimize for low override rate: reviewers who always agree may indicate
automation bias. Review sampled cases independently and keep monitoring health
separate from model-performance monitoring.
