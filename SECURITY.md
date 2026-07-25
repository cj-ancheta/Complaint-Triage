# Security policy

## Supported scope

This repository is an educational, manual-review-only research artifact. It has
no deployed API, public input form, or authorized automated routing system. The
latest `main` branch receives security and dependency updates; historical
commits are immutable evidence and are not separately patched.

## Report a vulnerability

Do not open a public issue containing a secret, complaint narrative, complaint
identifier, exploit payload, or private system detail. Use the repository's
private GitHub vulnerability-reporting channel when available. Otherwise,
contact the repository owner privately through the contact method on the GitHub
profile and include only the minimum evidence required to reproduce the issue.

Expect an acknowledgement within seven calendar days. Remediation priority is
based on exploitability, data exposure, evidence-integrity impact, and whether
the affected control is active or only designed. No bug-bounty payment or
production service-level commitment is offered.

## Disclosure and evidence boundary

The owner will coordinate disclosure after a fix or documented risk decision.
Security reports must not be used to justify access to governed local CFPB data,
the frozen test partition, ignored model artifacts, credentials, or another
person's system. Aggregate commit-safe evidence may be retained; raw sensitive
values must not enter Git or CI logs.

## Ownership and reuse

Repository-wide review ownership is declared in `.github/CODEOWNERS`. The
standalone `LICENSE` preserves all rights and permits inspection only; it does
not grant deployment, redistribution, data, or model-artifact rights.
