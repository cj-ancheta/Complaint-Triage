# Security and Privacy Assessment

- Assessment version: `1.0.0`
- Scope: current local ML repository and controls required for a future API/web
  demonstration
- Current network release: none
- Current authorization: offline research and aggregate governance evidence only

## Security objectives

Protect complaint narratives and credentials; preserve the integrity and lineage
of data, code, models, policies, and reports; prevent unauthorized model use;
fail safely when components are unavailable or mismatched; and avoid presenting
research evidence as a production guarantee.

## Assets and trust boundaries

Sensitive or integrity-critical assets include raw/public complaint narratives,
database credentials, PostgreSQL rows, model and calibrator artifacts, source and
split manifests, evaluation reports, future API credentials, reviewer audit
records, and release approvals.

Current boundaries:

```text
Internet CFPB source
  -> bounded acquisition code
  -> ignored local files
  -> loopback-only PostgreSQL Docker port
  -> local training/evaluation processes
  -> aggregate Git-safe reports and governance documents

No public API or frontend integration exists.
```

The local operating-system user and Docker administrator can access retained
data. Repository controls do not provide disk encryption or endpoint security.

## Threat model

| Threat actor/event | Path | Potential effect | Current boundary | Required future control |
|---|---|---|---|---|
| Accidental contributor | Commits raw data, secret, narrative, vocabulary, model, or log | Privacy breach or artifact exposure | `.gitignore`, aggregate contracts, review | Secret scanning, pre-commit/DLP, CI artifact review |
| Malicious/curious API user | Oversized, malformed, encoded, HTML-like, repeated, or probing input | Denial of service, unsafe rendering, extraction, privacy leakage | No API exists | Body/character/token limits, content type, escaping, timeout, rate limits, abuse monitoring |
| Compromised dependency/model cache | Package, base model, container, or artifact tampering | Code execution or changed predictions | Pinned model revision and artifact hashes | Lockfiles, hashes, SBOM, signed images/artifacts, vulnerability scanning |
| Network attacker | Intercepts future API traffic or exploits permissive CORS | Narrative/credential theft or unauthorized calls | Loopback database; no public service | HTTPS, explicit origins, authentication decision, secure headers, network isolation |
| Insider/local compromise | Reads Docker volume, `.env`, ignored data, or artifacts | Sensitive narrative/credential exposure | Local-only policy and deletion deadline | Least privilege, encrypted device, access review, incident response |
| Poisoned/corrupt source | Alters training data, labels, duplicates, or volume | Model degradation or hidden behavior | Content addressing, schema/reconciliation, append-only outcomes | Provenance review, anomaly thresholds, independent samples |
| Misconfiguration/outage | Wrong port, model mismatch, missing monitor, unavailable dependency | Silent failure or inconsistent routes | Fail-closed commands; manual fallback | Readiness, identity endpoint, monitoring health, tested rollback |
| Misleading publication | Screenshots/README/resume omit research boundaries | Stakeholder deception or unsafe adoption | Claims flags and governance pack | Mandatory claim review and artifact links |

## Current control status

| Control | Status | Evidence or limitation |
|---|---|---|
| Raw/intermediate/model paths excluded from Git | Implemented locally | `.gitignore`; governed artifacts remain local |
| Secrets excluded from Git | Implemented locally | `.env` ignored; `.env.example` contains placeholders |
| Database network exposure | Implemented locally | PostgreSQL published only on `127.0.0.1` |
| Append-only and reconciled data layers | Implemented | Migrations, manifests, reports, tests |
| Source/report/artifact hash verification | Implemented for governed workflows | Versioned commands fail closed on mismatch |
| Safe aggregate error responses | Implemented for current CLIs | Raw narratives, row predictions, and exception text are suppressed |
| Row-level public logging prohibition | Documented and tested in current reports | No public API exists yet |
| Raw-data deletion deadline | Approved; execution pending | ADR 0009 deadline 2026-11-19 |
| API validation, timeouts, generic errors | Required | Phase 5 not implemented |
| Authentication/authorization | Undecided and not implemented | Explicit approval required before design |
| Rate limiting and abuse controls | Required | No public service exists |
| CORS allowlist and HTTPS | Required | No public service exists |
| Secret scanning | Implemented in QA-105 CI | Full-history redacted Gitleaks scan plus ephemeral controlled rejection fixture |
| Dependency/SBOM/image scanning | Implemented in QA-105 CI | Strict installed-package audits, privacy-checked CycloneDX SBOMs, and actionable HIGH/CRITICAL Trivy gate |
| Dependency updates and workflow integrity | Implemented in QA-105 | Weekly Dependabot checks, immutable Action commits, digest-pinned scanner/base images |
| Security monitoring and incident response rehearsal | Required | No deployed environment exists |

## Secrets handling

Store local database secrets only in ignored `.env` configuration. A deployed
service must use provider-managed secrets or server-side environment variables,
least-privileged service identities, documented rotation, and separate
development/production values. Never put secrets, database credentials, private
API keys, or privileged URLs in `VITE_*` variables, Lovable prompts, frontend
code, committed files, screenshots, issues, logs, or model metadata.

Credential exposure requires immediate rotation, log/artifact assessment, and
incident recording; deleting the committed secret alone is insufficient.

## Input validation and output safety

A future API must accept a versioned JSON request with a string narrative and
reject missing, empty, binary, malformed, unsupported-encoding, or oversized
input before model work. Character, byte, request-body, and execution-time limits
must be explicit. Normalize encoding for processing while preserving the
original only inside an authorized case system. Treat narrative HTML/Markdown as
plain text and escape it in every UI.

Return generic internal errors with request IDs. Do not echo a rejected narrative
or include token IDs, logits, stack traces, paths, SQL, secrets, or model-cache
details. A model identity mismatch or unavailable monitor must produce the
unavailable/manual-review state, never a best-effort suggestion.

## Logging and redaction

Routine service logs may contain timestamp, request ID, route, status, latency,
active versions, aggregate counters, and controlled error codes. They must not
contain public-demo narratives, complaint IDs from the source data, tokens,
logits, free-text reviewer notes, authorization headers, cookies, secrets, or
full request bodies.

Debug logging is not a privacy bypass. Any exceptional row-level diagnostic needs
a separate approved secure environment, named owner, access restriction,
retention period, and deletion evidence.

## API, CORS, and rate-limit boundary

The authentication design remains phase-gated. A public fixture-only demo and an
authenticated operational reviewer service have different risks and must not
share an accidental default. CORS must list exact trusted HTTPS origins; wildcard
credentialed CORS is prohibited. Rate limits should constrain request count,
concurrency, and cost per identity/IP while avoiding raw-input storage.

Health may reveal only service status. Readiness must verify compatible model,
tokenizer, calibrator, taxonomy, and policy identities. Model-info may expose
approved summary metadata but not filesystem paths, secrets, or local artifact
locations.

## Dependency and artifact security

Pin the production Python, model revision, tokenizer, database image, OS/base
image, and frontend lockfile. Verify hashes before loading model/calibrator
artifacts. Produce an SBOM, scan packages and container images, review critical
advisories, and define a patch SLA. A dependency upgrade that can change tokens,
numerics, serialization, or predictions requires replay and model-change review,
not only a vulnerability scan.

## Incident response

1. Disable model suggestions and preserve manual review.
2. Contain exposed credentials, network paths, artifacts, or retained data.
3. Preserve non-sensitive audit evidence and identify affected versions/time.
4. Assess privacy, integrity, routing, and public-claim impact.
5. Notify the responsible data, security, model, operations, and governance roles.
6. Rotate secrets, remove unauthorized copies, patch in a new version, and verify
   deletion where required.
7. Rerun applicable tests and obtain fresh approval before reactivation.
8. Record lessons without publishing narratives or exploitable details.

No incident shortcut may activate a model, weaken oversight, extend retention,
or permit unsupported public claims.
