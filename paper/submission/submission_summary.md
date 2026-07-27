# External submission summary

## One-sentence contribution

The study shows how temporal validation, duplicate isolation, calibration,
route-level abstention safeguards, privacy controls, and software assurance can
change an apparently strong complaint classifier into a defensible no-go
decision, then defines the randomized evaluation needed to measure actual
human-workflow effects.

## Abstract

Aggregate classifier accuracy does not establish that an AI-assisted routing
workflow is safe or useful. We study financial complaint triage using a
duplicate-isolated temporal validation design and compare TF-IDF logistic
regression with a compact MiniLM classifier. The transformer improves validation
macro F1 and worst-class recall while providing similar aggregate accuracy to
the baseline, and temperature scaling improves later-month calibration without
changing predicted labels. However, every tested confidence-abstention policy
fails at least one predeclared class-aware safeguard. The operational conclusion
is therefore manual review only, not deployment. We connect that negative result
to the repository controls required for traceable evidence and specify a
prospective randomized target-trial blueprint with intention-to-treat estimands,
independent outcome adjudication, contamination-aware assignment, and
route-specific safety constraints. The current data contain neither randomized
assistance exposure nor downstream reviewer outcomes; accordingly, we report no
causal effect. The contribution is a reproducible example of decision-relevant
validation and a concrete protocol for testing whether governed model
suggestions improve reviewer correctness or handling time without worsening a
required route.

## Why the result matters

The central result is actionable despite being negative. A global metric could
support a persuasive demo while hiding that the suggestion policy supplied no
eligible cases for one required category at a tested threshold. Keeping the
manual workflow is therefore an evidence-based decision, not an absence of
progress. The paper makes the safety constraint visible and prevents validation
metrics from being promoted into unmeasured claims about people or operations.

## Novelty and evidence

The paper's novelty is the integration of four layers that are often reported
separately: predictive comparison, probability calibration, selective-policy
eligibility, and evidence/software governance. Its empirical claims are backed
only by committed aggregate reports and deterministic figures. Its causal
section contributes an executable design logic—treatment, outcomes, estimands,
assignment, analysis, and stopping rules—but deliberately contributes no effect
estimate because the required intervention data do not exist.

## Scope boundaries for editors and reviewers

- This is a validation-only case study, not a frozen-test evaluation.
- It does not demonstrate deployment benefit, reviewer productivity, or
  demographic fairness.
- The causal protocol is
  `design_blueprint_not_registered_not_conducted`.
- The proposed treatment is reviewer access to a governed suggestion; model
  confidence and reviewer interaction are post-assignment mediators, not
  baseline adjustment variables.
- The negative abstention result and manual-review-only decision are core
  findings and must not be removed to make the narrative appear more positive.

## Suggested article classification

Applied machine learning case study; responsible AI and model governance;
human-AI decision support; prospective evaluation protocol.
