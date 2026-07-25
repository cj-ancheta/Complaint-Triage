# Problem Statement

## Decision being supported

The research system estimates a CFPB complaint product category from a financial
complaint narrative. A future release could abstain under an approved calibrated
confidence policy; no threshold is currently approved, so all cases remain
manual.

A human reviewer remains responsible for accepting, correcting, or escalating the route.

## Intended users

- complaint operations reviewers;
- model owners;
- AI governance and risk reviewers.

## Intended benefit

The project will investigate whether a measured and supervised NLP suggestion can make routine routing easier while keeping uncertainty, limitations, and reviewer authority visible.

No operational benefit has been measured yet.

## Potential harms

- a complaint is routed incorrectly and review is delayed;
- an overconfident score encourages automation bias;
- taxonomy or language drift weakens performance;
- public users submit personal information to a demo;
- explanations are mistaken for causal reasoning;
- aggregate performance conceals weak product classes;
- the source database is treated as representative when it is not;
- portfolio language overstates research evidence as production impact.

## Non-goals

The system does not determine truth, liability, compensation, consumer vulnerability, legal outcome, or response wording. It does not automatically close or reject complaints.

## Current evidence status

Phases 0 through CT-401 are complete for the retained research run
`cfpb-run-20260722T130728Z-2b7815d4c850`. The project has reconciled source,
population, duplicate-isolated temporal splits, classical and compact
transformer candidates, calibration, operational model selection, and a fixed
abstention-policy analysis.

Calibrated MiniLM is the selected research candidate, but no confidence
threshold passed every approved global and class-aware gate. The accepted
system status is therefore `manual_review_only`: it is not authorized to
suggest or automatically route a complaint. The frozen test partition remains
untouched, no API or public application exists, and no deployment, reviewer
productivity, downstream impact, or public performance claim is approved.

The current release decision and evidence lineage are indexed in
[`governance_pack.md`](governance_pack.md).
