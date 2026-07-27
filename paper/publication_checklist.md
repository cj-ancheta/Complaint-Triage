# Public preprint release checklist

Release: `paper-v1.0.1`

Authorization date: 2026-07-26

## Identity and scope

- [x] Title identifies decision impact, validation governance, and the causal
  evaluation blueprint.
- [x] Author and contribution statement are present.
- [x] `CITATION.cff` supplies versioned citation metadata.
- [x] Abstract and title page label the empirical study validation-only.
- [x] No frozen-test, deployment, demographic-fairness, or production claim is
  made.

## Empirical reporting

- [x] Population construction, duplicate handling, temporal split, model
  selection, calibration, and abstention policy are reproducible from committed
  aggregate evidence.
- [x] Accuracy is reported with macro F1, weighted F1, worst-class recall, and
  per-class evidence.
- [x] The failed class-aware threshold policy and manual-review-only outcome are
  retained as the main decision result.
- [x] Every empirical display is deterministically generated and source-bound.
- [x] Prediction-reporting principles adapted from TRIPOD+AI are accompanied by
  a non-clinical scope caveat.

## Impact and causal claims

- [x] The paper distinguishes prediction from intervention effects.
- [x] The current data are explicitly stated to lack treatment assignment,
  reviewer behavior, and downstream outcomes.
- [x] RQ5 defines a prospective target trial, intention-to-treat estimands,
  independent outcome adjudication, contamination-aware assignment, and
  route-specific safety constraints.
- [x] F7 distinguishes baseline variables, randomized assignment,
  post-assignment mediators, and outcomes.
- [x] The causal appendix is labelled
  `design_blueprint_not_registered_not_conducted`.
- [x] No sample size, effect direction, causal estimate, trial completion, or
  transport of external effect sizes is claimed.

## Privacy, ethics, and governance

- [x] The public package contains no narratives, complaint identifiers,
  row-level values, prediction arrays, vocabulary, or local explanations.
- [x] Model suggestions, automated routing, and reviewer exposure remain
  unauthorized.
- [x] The raw-data retention deadline and deletion evidence workflow remain in
  force.
- [x] AI-assisted authoring is disclosed and human responsibility is explicit.
- [x] Repository license and third-party rights are not expanded by release.

## Reproduction and release

- [x] `python paper/scripts/generate.py --check`
- [x] Paper planning, citation, causal-boundary, and figure tests
- [x] Full local test suite
- [x] Ruff lint and format checks
- [x] Protected `standard`, `transformer-cpu`, and `security` jobs
- [x] Squash merge to protected `main`
- [x] GitHub release tag `paper-v1.0.0` established the public preprint.
- [x] A reproducible tagged-source renderer produces self-contained HTML, PDF,
  and a SHA-256 artifact manifest.
- [x] DOI-deposit metadata, rights instructions, submission summary, and
  immutable-file verification steps are committed.
- [x] Final-package automation requires tag/version/DOI agreement, copies
  supplementals from the immutable tag, and hashes every deposited file.
- [x] PDF hardening validates structure and normalizes metadata time to the
  tagged source commit.
- [ ] The owner has reserved the Zenodo DOI and supplied it for inclusion in
  version 1.0.2 before the final tag is created.
- [ ] The owner has authenticated to Zenodo, reviewed the reserved DOI and
  record preview, and pressed Publish. This account-bound action cannot be
  delegated and remains outside repository authorization.

The repository release is the publication venue for version 1.0.1. The DOI
deposit must use the exact release files and checksums. A later journal
submission may cite this immutable release but must not alter the evidence
interpretation without a new version and review.
