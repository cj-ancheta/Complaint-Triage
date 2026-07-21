# Phase 0 Review

## System summary

The planned product is a human-in-the-loop classifier for public financial complaint narratives. It suggests a product route, exposes confidence and model metadata, and abstains when it lacks sufficient confidence. Human reviewers keep final authority.

## Phase 0 scope

Implemented in this checkpoint:

- local Git repository;
- full specification;
- controlled AI-assisted coding rules;
- Python package scaffold;
- lint, format, test, and coverage configuration;
- smoke test;
- GitHub Actions validation;
- documentation skeleton;
- architecture decisions;
- issue backlog.

Explicitly not implemented:

- data download or ingestion;
- database;
- modelling;
- evaluation;
- FastAPI;
- Lovable frontend;
- deployment;
- public metrics.

## Unresolved decisions

These should be resolved only when their phase requires them:

1. Exact CFPB API/export fields and current schema.
2. Stable modelling date window.
3. Target product taxonomy and taxonomy versioning.
4. Narrative language-filtering method.
5. Duplicate and near-duplicate isolation method.
6. PostgreSQL local/deployment configuration.
7. Experiment tracking storage design.
8. Availability and value of GPU training.
9. Model-selection utility weights.
10. Abstention threshold.
11. Public-demo retention and review-feedback policy.
12. API authentication and rate limiting.
13. Deployment provider and cost ceiling.
14. Final Lovable API proxy design.
15. Open-source license choice.

## Environmental findings

- Git is installed.
- Python 3.10, 3.13, and 3.14 are installed.
- Python 3.13 is selected for local development.
- `uv` is not installed.
- Phase 0 uses standard `venv` and `pip` to avoid an unnecessary global tool installation.

## Immediate risk controls

- raw and processed data paths are ignored by Git;
- model artifacts and experiment stores are ignored;
- real `.env` files are ignored;
- no runtime dependency is added before its need is established;
- agents must stop at data, model, security, and public-claim gates;
- commits require explicit user approval after review.

## Recommended next issue

CT-101: investigate the current CFPB API/export schema without downloading the full dataset.

The output should be a source field inventory, schema/version observations, privacy notes, and a proposal for a bounded profiling request. It should not add database ingestion or modelling.

