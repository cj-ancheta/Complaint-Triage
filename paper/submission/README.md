# DOI deposit and external-submission handoff

Status: `final_source_doi_bound`

Reserved DOI: `10.5281/zenodo.21670879`

Final deposit version: `1.0.2`

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

Version 1.0.1 is a public submission candidate, not the file set to publish on
Zenodo. The final package must include the DOI reserved for the Zenodo draft.
This follows Zenodo's supported reserve-first workflow and avoids publishing a
PDF whose persistent identifier is missing.

The DOI is reserved and embedded in the reviewed source. After the immutable
tag is created, the final release build is generated locally and intentionally
ignored by Git:

```powershell
.\paper\scripts\build_submission.ps1 -Version 1.0.2 -Doi 10.5281/zenodo.21670879
```

The command will reject placeholder, missing, or malformed identifiers. It creates
`paper/release-build/v1.0.2/`, loads every source file directly from the
immutable `paper-v1.0.2` tag, normalizes PDF metadata time to the source commit,
and checks the completed package twice. Only that directory is eligible for
deposit.

## Recommended DOI path

1. Keep the existing Zenodo draft containing reserved DOI
   `10.5281/zenodo.21670879`; do not create a second DOI.
2. Use resource type **Publication / Preprint** and fill the reviewed metadata.
3. Run the hardened build command above after tag `paper-v1.0.2` exists. Upload
   the PDF as the primary file and
   the HTML, both manifests,
   `CITATION.cff`, impact statement, prospective causal protocol, and generated
   source manifest as supplementary files. Use public file visibility and the
   custom rights statement in [`deposit_metadata.md`](deposit_metadata.md); do
   not accept Zenodo's default CC BY license because this repository is
   explicitly All rights reserved.

Preview the record and compare every file and field against
[`pre_publish_verification.md`](pre_publish_verification.md). The owner must then
press **Publish** while authenticated. Zenodo makes record metadata editable
after publication, but the files and persistent identifier are immutable; a
file correction therefore requires a new record version.

Do not add a root `.zenodo.json` for this paper deposit. That file controls
GitHub software-release archiving and would override the repository's existing
`CITATION.cff`. A software DOI may be created separately later, but it should
not be confused with the Publication / Preprint DOI.

After publication, verify that the DOI resolves and that Zenodo's displayed
checksums match `submission-manifest-v1.0.2.json`. Because the reserved DOI is
already in the tagged files, no post-publication file replacement is required.

## Authoritative deposit guidance

- [Reserve a DOI before publication](https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/)
- [Use the first-publication date](https://help.zenodo.org/docs/deposit/describe-records/publication-date/)
- [Select or define licenses and rights](https://help.zenodo.org/docs/deposit/describe-records/licenses/)
- [Understand record and file immutability](https://help.zenodo.org/docs/deposit/about-records/)
