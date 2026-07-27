# Pre-publication verification

Complete this check against the Zenodo preview immediately before Publish.

## Identity and metadata

- [ ] The title and creator exactly match `CITATION.cff`.
- [ ] Resource type is Publication / Preprint, version is 1.0.2, and the
  publication date is 2026-07-26, the first public preprint release date.
- [ ] The related identifier points to the public `paper-v1.0.2` release.
- [ ] The same reserved DOI appears in the preview, tagged `CITATION.cff`,
  manuscript title block, deposit metadata, HTML, and submission manifest.

## Files and provenance

- [ ] Every uploaded filename is listed in `deposit_metadata.md`.
- [ ] The artifact and submission manifests identify `paper-v1.0.2` and their
  source commit equals `git rev-list -n 1 paper-v1.0.2`.
- [ ] The submission directory contains exactly the eleven allowlisted files.
- [ ] Every local SHA-256 hash matches `submission-manifest-v1.0.2.json`.
- [ ] The PDF opens, figures and tables are legible, hyperlinks are sensible,
  and the final release footer is visible.
- [ ] The HTML opens without a network connection and all seven figures render.
- [ ] No raw data, identifiers, row-level outputs, model artifacts, credentials,
  or ignored local files are present.

## Claims and rights

- [ ] The description says validation-only, manual-review-only, and no causal
  effect.
- [ ] The prospective protocol is labelled
  `design_blueprint_not_registered_not_conducted`.
- [ ] File visibility is Public and the rights field is the custom All rights
  reserved statement; Zenodo's default CC BY license has been removed.
- [ ] The record preview does not imply peer review, trial registration,
  deployment, frozen-test performance, or demonstrated workflow impact.

## Irreversible action

- [ ] The owner has reviewed the complete preview and understands that Zenodo
  permits later metadata edits but not ordinary replacement of published files.
- [ ] The owner presses Publish while authenticated, verifies that the reserved
  DOI resolves, and compares Zenodo's displayed checksums with the submission
  manifest.
