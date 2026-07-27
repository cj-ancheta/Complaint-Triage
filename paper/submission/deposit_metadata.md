# Zenodo deposit metadata

Use these values in a new manual deposit. They are a review sheet, not an API
payload.

| Field | Value |
|---|---|
| Resource type | Publication |
| Publication subtype | Preprint |
| Title | When Aggregate Accuracy Is Not Enough: Decision Impact, Validation Governance, and a Causal Evaluation Blueprint for Financial Complaint Triage |
| Creator family name | Ancheta |
| Creator given names | Charles Jr |
| Publication date | 2026-07-26 (date of first public preprint release) |
| Publisher | Zenodo |
| Version | 1.0.2 |
| Language | English |
| File visibility | Public |
| License/rights | Custom: All rights reserved |
| Related identifier | `https://github.com/cj-ancheta/Complaint-Triage/releases/tag/paper-v1.0.2` |
| Related-identifier relation | Is supplemented by |
| DOI status | Awaiting owner reservation; do not publish until the actual DOI replaces this status |

## Description

This validation-only case study examines an imbalanced financial-complaint
routing system as a decision and governance problem rather than an aggregate
accuracy contest. It compares TF-IDF logistic regression with compact MiniLM
under temporal separation and duplicate isolation, evaluates probability
calibration and class-aware abstention, and documents a consequential negative
result: no tested suggestion threshold satisfied every required safeguard, so
the system remains manual-review-only. The paper also specifies a prospective
randomized target-trial blueprint for estimating whether AI suggestions change
reviewer correctness and handling time without harming any required route.
That trial is not registered or conducted, and the paper reports no causal
effect. Evidence is aggregate and validation-only; frozen-test performance,
deployment efficacy, and demographic fairness are not claimed.

## Keywords

- financial complaint triage
- imbalanced text classification
- selective classification
- probability calibration
- model governance
- human-AI decision support
- target trial
- causal inference
- abstention
- validation-only evaluation

## Custom rights statement

Copyright (c) 2026 Charles Jr Ancheta. All rights reserved. The record is
publicly viewable for portfolio review and educational inspection, but no
permission is granted to copy, modify, distribute, sublicense, sell, deploy, or
otherwise reuse the deposited files without the copyright holder's prior
written permission. Third-party packages, source data, and referenced works
remain subject to their own licenses and terms.

## Files

Upload the exact versioned files below from
`paper/release-build/v1.0.2/` after the final gate passes:

1. `when-aggregate-accuracy-is-not-enough-v1.0.2.pdf` — primary preview file.
2. `when-aggregate-accuracy-is-not-enough-v1.0.2.html` — self-contained
   accessible rendering.
3. `release-artifact-manifest-v1.0.2.json` — renderer output hashes.
4. `submission-manifest-v1.0.2.json` — complete deposit allowlist and hashes.
5. `CITATION-v1.0.2.cff` — citation metadata.
6. `manuscript-v1.0.2.md` — preservation-friendly paper source.
7. `impact-statement-v1.0.2.md` — concise decision relevance.
8. `prospective-causal-protocol-v1.0.2.md` — not-conducted causal design.
9. `paper-source-manifest-v1.0.2.json` — aggregate-evidence provenance.
10. `submission-summary-v1.0.2.md` — reviewed archive abstract and boundaries.
11. `zenodo-deposit-metadata-v1.0.2.md` — this metadata and rights record.

Do not upload raw complaints, complaint identifiers, row-level predictions,
model artifacts, vocabulary, local explanations, secrets, or ignored raw data.
