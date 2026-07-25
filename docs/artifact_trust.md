# Trusted-local artifact boundary

Status: QA-110 accepted; GitHub Actions run 30164993961 passed

The repository does not accept model artifacts from uploads, URLs, pull
requests, CI artifacts, or other users. Governed model files live only under
ignored local directories and are loaded for the validation-only workflow.
This is a trust boundary, not a claim that a SHA-256 digest authenticates the
person or process that created a file.

## Enforced path boundary

Every executable or stateful artifact load resolves a canonical POSIX-relative
path beneath its exact approved directory:

- `artifacts/cfpb/tfidf-logreg/` for the joblib baseline; and
- `artifacts/cfpb/transformer/` for model, calibration, and resume artifacts.

Absolute paths, traversal, backslash aliases, prefix lookalikes, and symbolic
links are rejected before deserialization. Existing size and SHA-256 checks
then prove the local bytes match the governed manifest. They provide integrity
against accidental change, not authenticity against an attacker who can edit
both the artifact and its manifest.

## Serialization decision

New and existing transformer model weights use Safetensors. Calibration state
uses JSON. The training-resume file must preserve optimizer, scheduler, scaler,
Python/NumPy/Torch random-number-generator, and tensor state, so it remains a
PyTorch checkpoint. It is now read with `weights_only=True`; arbitrary pickle
globals are disabled. A narrow compatibility allowlist covers only the NumPy
array/dtype machinery present in the accepted RNG state. The existing governed
epoch-3 resume file loads under this restriction, while a non-allowlisted class
is rejected by a controlled error.

The TF-IDF scikit-learn pipeline remains joblib because its fitted estimator
graph is not representable as simple JSON or Safetensors without replacing the
accepted artifact and inference implementation. Therefore it is loaded only
after exact-directory, link, size, digest, software-version, pipeline-type, and
named-step checks. Do not expose that loader through a service or use it on a
downloaded file.

## Maintainer rules

- Never copy a model file and its manifest from an untrusted source and treat
  the recorded hash as authentication.
- Never weaken `weights_only=True` or broaden the safe-global list merely to
  load an unknown checkpoint.
- Reject a new artifact format unless its origin, path, identity, retention,
  and deserialization behavior are reviewable and tested.
- Keep local artifacts ignored and delete them with the governed retention
  workflow. CI uses synthetic fixtures and does not load these files.

GitHub Actions run
[`30164993961`](https://github.com/cj-ancheta/Complaint-Triage/actions/runs/30164993961)
passed the standard, CPU-transformer, and security gates with the restricted
loader and malicious-path contracts enabled.
