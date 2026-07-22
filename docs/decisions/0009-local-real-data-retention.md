# ADR 0009: Local-only 120-day real-data retention

- Status: Accepted
- Date: 2026-07-22
- Decision owner: Charles Jr Ancheta
- Policy ID: `cfpb-local-120d-v1`
- Deletion deadline: 2026-11-19 end of day, Asia/Singapore
- Scope: the first bounded real CFPB extract and locally derived row-level text

## Context

The raw loader has remained synthetic-only because public complaint narratives
can still contain sensitive personal experiences after CFPB publication
processing. Reproducible modelling needs a bounded local extract, but indefinite
retention, cloud synchronization, or casual backup is unnecessary for this
portfolio project.

ADR 0008 is accepted, so a real staged batch is now needed to measure population
attrition. This policy authorizes retention; it does not by itself authorize an
untested network writer. CT-108 must enforce the manifest boundary and CT-109
must prove streaming and cleanup before downloading or loading real rows.

## Decision

Authorize policy `cfpb-local-120d-v1` for the first bounded real extract.

Covered data may exist only on Charles's local development machine and includes:

- temporary download files;
- content-addressed raw CFPB response artifacts;
- raw and staging PostgreSQL rows containing narratives;
- row-level analytical or split artifacts that reproduce source text; and
- token vocabularies or diagnostic exports that retain uncommon source strings.

The absolute deletion deadline is the end of 2026-11-19 in Asia/Singapore. A
batch manifest must record this policy ID, retrieval time, and computed expiry.
No covered artifact may extend the deadline merely because it was copied or
transformed later.

Covered data must not be:

- committed to Git;
- placed in GitHub releases or CI artifacts;
- uploaded to cloud object storage, notebooks, shared drives, or experiment
  services;
- included in system or application backups; or
- pasted into issues, documentation, logs, screenshots, prompts, or the public
  web application.

Permitted retained evidence after deletion:

- source request and commit-safe manifests without row values;
- hashes, byte counts, schema versions, and aggregate counts;
- aggregate evaluation, drift, and exclusion reports;
- source code, tests, decision records, and synthetic fixtures; and
- model artifacts only when they do not contain recoverable narratives or a
  source-derived token vocabulary.

## Storage boundary

Real data is permitted only in ignored paths under the repository's declared
`data/` boundary and the loopback-only project PostgreSQL Docker volume. The
frontend repository, browser storage, Lovable, CI, and any deployed service are
outside the authorized boundary.

Disk encryption is not provided by this repository. The local operating-system
and Docker administrators can access the data. If the machine is lost,
compromised, shared, or sent for repair while covered data exists, processing
must stop and the incident must be recorded.

## Deletion and evidence

The project maintainer owns cleanup. By the deadline, cleanup must:

1. resolve and verify the exact ignored real-data paths;
2. remove temporary and content-addressed real artifacts;
3. remove the project PostgreSQL volume, thereby deleting raw, staging,
   analytical, and split row data together;
4. remove governed text-bearing derived artifacts;
5. verify that covered paths, database volume, and containers no longer exist;
   and
6. write a commit-safe deletion record containing timestamps, policy ID, batch
   IDs, artifact hashes, and verification results, but no narrative text.

Cleanup must use a dedicated, tested command with explicit target checks. It
must not rely on a broad recursive deletion, `$HOME`, the workspace root, an
unresolved environment variable, or a hand-assembled cross-shell path list.

## Backups and recovery

No backup of covered data is authorized. Deletion is intentionally irreversible.
If reproduction is later required, create a new bounded extract with a new
manifest and an approved active retention record rather than restoring old data.

## Consequences

Benefits:

- a real population report can be produced without indefinite row-level storage;
- the storage and expiry boundary is explicit and auditable;
- aggregate portfolio evidence can survive cleanup;
- deletion at the database-volume boundary is compatible with append-only
  tables during the active retention period.

Costs and risks:

- exact row-level reproduction ends after deletion;
- all project database layers in the volume are deleted together;
- the user must avoid automatic cloud backup or synchronization outside the
  repository's control;
- model/token artifacts require inspection before they are retained; and
- the fixed deadline may require re-extraction if project work runs late.

## Implementation gate

Before the first real request, CT-108 and CT-109 must add tests that reject:

- an unknown or missing policy ID;
- an expiry later than the approved deadline;
- a real artifact outside the allowed local path;
- a manifest that contains row values; and
- any attempt to log or commit a response body.

CT-109 must also implement the exact cleanup and deletion-evidence workflow.
Until those controls pass, no live acquisition command may run.
