# Main branch protection

Status: QA-104 accepted and remotely verified on 2026-07-25

The public repository's `main` branch is protected through GitHub's branch
protection API. The active policy requires:

- strict successful `standard` and `transformer-cpu` status checks;
- pull-request delivery, including for repository administrators;
- linear history and resolved review conversations; and
- force pushes and branch deletion to remain disabled.

The API verification immediately after configuration returned protection
enabled, strict checks enabled, both exact job contexts, administrator
enforcement enabled, pull requests required, zero mandatory external approvals,
linear history enabled, conversation resolution enabled, force pushes disabled,
and deletion disabled.

Zero mandatory approvals is deliberate for this single-owner portfolio. The
pull request is still the review container and both CI jobs are mandatory, but
the owner is not forced to manufacture a second identity or self-approval. A
future multi-contributor repository should require at least one independent
approval and CODEOWNERS for governance-sensitive paths.

## Recovery boundary

Routine bypass is not authorized. If a broken workflow prevents all merges, the
owner may temporarily change protection only after recording the incident,
reason, exact prior policy, recovery commit, and restoration evidence. Force
push and deletion remain prohibited during recovery. The normal policy must be
restored immediately after the minimum repair and verified through the API.

QA-105 and later changes use feature branches and checked pull requests. This
document records the control but is not a credential, enforcement mechanism, or
substitute for querying the current GitHub API state.
