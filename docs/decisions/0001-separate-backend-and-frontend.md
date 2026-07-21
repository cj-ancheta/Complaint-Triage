# ADR 0001: Separate ML Backend and Lovable Frontend

- Status: accepted
- Date: 2026-07-21

## Context

The project needs a Python data and model pipeline plus a polished public interface. Lovable creates a React application and can synchronize it to a GitHub repository. The model requires Python libraries and server-side controls that should not be bundled into a browser application.

## Decision

Use two repositories:

- `complaint-triage-ml` for ingestion, SQL, modelling, evaluation, API, tests, and governance;
- `complaint-triage-web` for the Lovable React interface.

Connect them through a versioned HTTP API. If a secret is needed, introduce a server-side proxy or Edge Function rather than exposing it in frontend variables.

## Consequences

Benefits:

- clear security boundary;
- independent model and UI testing;
- Lovable generation cannot silently rewrite the ML pipeline;
- backend can be deployed according to model requirements;
- frontend can use fixtures before the API exists.

Costs:

- two repositories and deployments;
- API contract coordination;
- CORS and environment configuration;
- end-to-end tests require both services.

## Revisit trigger

Revisit only if a future hosting platform provides a demonstrably simpler secure monorepo workflow without moving model execution into the browser.

