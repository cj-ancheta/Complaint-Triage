# Problem Statement

## Decision being supported

The proposed system suggests a CFPB complaint product category from a financial complaint narrative. It can abstain when its calibrated confidence is below an approved threshold.

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

Phase 0 only. No source data, model, evaluation, API, or deployed interface exists yet.

