# Finalization status

State: `reserved_doi_embedded_final_source_ready`

Reserved DOI: `10.5281/zenodo.21670879`

Final deposit version: `paper-v1.0.2`

The evidence, prose, figures, causal protocol, rights boundary, portable
renderer, and final-package verifier are complete. The owner reserved DOI
`10.5281/zenodo.21670879`, and it is embedded in the final tagged-source
candidate. Publication remains pending the immutable tag, verified package,
Zenodo preview, and the owner's Publish action.

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

`build_submission.ps1` will succeed only after the reviewed source is merged and
tagged as `paper-v1.0.2`; it then verifies the DOI-bearing package twice.
