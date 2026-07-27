# DOI deposit and external-submission handoff

Status: `package_ready_doi_not_minted`

Paper version: `1.0.1`

Source release: `paper-v1.0.1`

This folder turns the reviewed paper into a controlled submission package. It
does not claim that a causal trial was run. The publishable impact is the
decision consequence of the validation evidence: the tested suggestion policy
failed a required route safeguard, so the system remains manual-review-only.
The causal contribution is a prospective, falsifiable evaluation protocol.

## Package contents

- [`deposit_metadata.md`](deposit_metadata.md) gives the exact Zenodo fields.
- [`submission_summary.md`](submission_summary.md) provides the abstract,
  contribution statement, novelty, evidence limits, and suggested keywords for
  an archive or venue form.
- [`pre_publish_verification.md`](pre_publish_verification.md) is the final
  immutable-file and preview check.

The release build is generated locally and intentionally ignored by Git:

```powershell
.\paper\scripts\build_preprint.ps1 -Tag paper-v1.0.1 -Version 1.0.1
```

The command creates a self-contained HTML file, a print PDF, and a JSON manifest
containing the source commit and SHA-256 hashes. Only artifacts whose manifest
resolves to the public `paper-v1.0.1` tag are eligible for deposit.

## Recommended DOI path

Create a manual Zenodo record with resource type **Publication / Preprint**.
Upload the PDF as the primary file and the HTML, artifact manifest,
`CITATION.cff`, impact statement, prospective causal protocol, and generated
source manifest as supplementary files. Use public file visibility and the
custom rights statement in [`deposit_metadata.md`](deposit_metadata.md); do not
accept Zenodo's default CC BY license because this repository is explicitly All
rights reserved.

Reserve the DOI, preview the record, and compare every file and field against
[`pre_publish_verification.md`](pre_publish_verification.md). The owner must then
press **Publish** while authenticated. Zenodo makes record metadata editable
after publication, but the files and persistent identifier are immutable; a
file correction therefore requires a new record version.

Do not add a root `.zenodo.json` for this paper deposit. That file controls
GitHub software-release archiving and would override the repository's existing
`CITATION.cff`. A software DOI may be created separately later, but it should
not be confused with the Publication / Preprint DOI.

After Zenodo assigns the DOI, add it to `CITATION.cff`, this README, and the
repository README in a metadata-only reviewed patch. No DOI is recorded before
Zenodo actually mints it.
