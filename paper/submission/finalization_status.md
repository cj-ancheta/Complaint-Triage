# Finalization status

State: `awaiting_owner_reserved_doi`

Current public version: `paper-v1.0.1`

Planned final deposit version: `paper-v1.0.2`

The evidence, prose, figures, causal protocol, rights boundary, portable
renderer, and final-package verifier are complete. Version 1.0.2 must not be
tagged or submitted until the owner reserves a DOI in the Zenodo draft and
provides the exact identifier for inclusion in the paper.

The hard gate intentionally requires all of the following to agree:

- semantic version and `paper-v<version>` tag;
- immutable tag commit and both provenance manifests;
- reserved DOI in `CITATION.cff`, manuscript, deposit metadata, rendered HTML,
  and final submission manifest;
- exactly seven embedded figures and no remote image dependency;
- a complete PDF of 15-40 pages with metadata time normalized to the source
  commit;
- exactly eleven allowlisted deposit files with byte sizes and SHA-256 hashes;
- validation-only, manual-review-only, not-conducted causal, and All rights
  reserved boundaries.

Until the DOI is supplied, `build_submission.ps1` must fail. That failure is a
release control, not an unfinished scientific result.
