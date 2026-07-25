# Model and System Change Management

- Procedure version: `1.0.0`
- Current release: research evidence only
- Current rollback state: `manual_review_only`

## Change classes

| Change class | Examples | Minimum decision boundary |
|---|---|---|
| Documentation-only | Typo or clearer wording without changing a claim | Peer review and evidence-link check |
| Patch | Bug fix that preserves data, model, taxonomy, policy, and API behavior | Tests, replay, owner review, patch version |
| Minor | New compatible diagnostic, monitoring view, or additive API field | Tests, security/privacy review, minor version |
| Major | Data source/window, taxonomy, exclusions, split, model family, calibration, threshold policy, retention, API semantics, authentication, deployment, or public claim | New ADR, explicit owner approval, full evidence cycle, major version |

Any ambiguity is resolved upward. A change that can alter who receives a model
suggestion or how a complaint is handled is not documentation-only.

## Versioning convention

Use semantic versions for source contracts, population, split, reports, model
cards, governance policies, API contracts, and deployments. Models additionally
record base revision, training run, selected epoch, artifact hash, tokenizer,
calibrator, taxonomy, and feature contract. Never overwrite accepted evidence;
publish a new identity.

## Promotion checklist

Every checkbox must have an artifact or named approval. “Not applicable” needs a
written reason.

- [ ] Intended and prohibited uses are current.
- [ ] Data source, collection, feature, label, retention, and deletion rules are
      approved.
- [ ] Taxonomy, population, duplicate, and temporal split versions are fixed.
- [ ] Source, code, environment, model, tokenizer, and calibrator identities
      reconcile.
- [ ] Unit, integration, privacy, security, schema, replay, and failure tests
      pass in the release environment.
- [ ] Candidate comparison follows a predeclared utility rule.
- [ ] Calibration and threshold policy are predeclared and pass every gate.
- [ ] A qualified owner explicitly approves the selected threshold.
- [ ] Frozen evaluation is run once without retuning and the result is accepted.
- [ ] Per-class, calibration, abstention, operational, and uncertainty evidence
      is reviewed.
- [ ] Human oversight, escalation, override recording, and manual fallback are
      operationally tested.
- [ ] Threat model, authentication decision, validation, rate limits, logging,
      redaction, dependency scanning, and incident response are reviewed.
- [ ] Monitoring rules, health/freshness checks, alert owners, and stop criteria
      are tested.
- [ ] Deployment provider, cost, concurrency, availability, recovery, CORS,
      HTTPS, and secrets boundaries are approved.
- [ ] Model card, data sheet, risk register, security notes, and release notes are
      updated.
- [ ] Every README, UI, portfolio, resume, screenshot, and demo claim traces to
      accepted evidence and carries the correct validation/final qualifier.
- [ ] Rollback and suggestion-suspension drills pass.
- [ ] The approver records a release, reject, or manual-only decision.

The current release fails the threshold, frozen-test, service, security,
monitoring, deployment, and public-claim gates. It must remain manual-only.

## Required tests by change

- Data changes: contract, schema, boundedness, reconciliation, privacy,
  retention, duplicate leakage, temporal leakage, and class-support tests.
- Model changes: deterministic fixtures, training smoke, metric implementation,
  artifact hash/load, calibration, threshold, replay, and regression tests.
- API changes: OpenAPI snapshot, validation, error, logging, privacy, rate-limit,
  authentication/CORS, timeout, and model-unavailable tests.
- Frontend changes: typed contract, fixture/real-mode separation, no-browser-
  secret check, keyboard/mobile, safe rendering, privacy notice, and suggestion/
  abstention/unavailable state tests.
- Infrastructure changes: image, SBOM, vulnerability, health, secrets, network,
  recovery, and rollback tests.

## Approvals and segregation

Charles is the current project owner and may approve research phase gates. A
real deployment should separate author, model approver, data steward, security
reviewer, and operations owner where practical. The same person must not silently
change a gate and then approve the result measured under that changed gate.

Public metric promotion, retention behavior, authentication, deployment provider,
and paid services always need explicit approval even if code tests pass.

## Rollback

The universal safe state is to disable suggestions and continue manual review.
A future service must support configuration or deployment rollback that does not
depend on the model being healthy. Rollback must preserve queued cases and audit
records, invalidate caches for the withdrawn version, expose the active version,
and prevent mixed model/calibrator/taxonomy identities.

After rollback:

1. record the trigger, time, affected version, and owner;
2. verify suggestions are disabled;
3. assess privacy, integrity, and routing impact;
4. notify reviewers with non-sensitive instructions;
5. repair in a new version and rerun required tests;
6. obtain fresh approval before reactivation; and
7. never erase the failed evidence or use frozen test outcomes for repair tuning.

## Emergency changes

Security containment, credential rotation, service disablement, and data cleanup
may occur immediately to reduce harm. Emergency status never authorizes a model,
threshold, feature, retention extension, or public claim. Document the action and
complete retrospective review before normal service resumes.
