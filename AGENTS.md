# Repository Instructions for AI Coding Agents

## Authority and source of truth

Read `SPEC.md` completely before beginning any implementation task. Treat it as the product and engineering source of truth.

Also read the files directly relevant to the active issue, including tests and decision records. If a request conflicts with `SPEC.md`, identify the conflict before editing.

## Working boundary

Work on one bounded issue at a time. Do not continue into the next issue or phase unless the user explicitly asks.

Before editing:

1. Summarize the current behavior and the requested outcome.
2. State assumptions, risks, and unresolved decisions.
3. Propose the smallest complete implementation plan.
4. Identify the tests that will prove the change.

After editing:

1. Run the narrowest relevant checks first.
2. Run the full repository validation when practical.
3. Explain every material file change in plain language.
4. Report commands run, results, limitations, and unresolved risks.
5. Suggest the next bounded issue but do not begin it.

## Mandatory rules

1. Do not modify unrelated files.
2. Do not weaken, delete, or bypass tests to make a build pass.
3. Do not fabricate datasets, metrics, screenshots, evaluation results, or impact claims.
4. Keep raw CFPB data, complaint narratives, secrets, model artifacts, and local experiment stores out of Git.
5. Explain every new dependency and why the existing stack is insufficient.
6. Add or update tests for every behavior change.
7. Preserve the versioned public API unless the active issue explicitly changes it.
8. Use temporal evaluation and prevent duplicate leakage when modelling begins.
9. Keep test data untouched during tuning.
10. Treat abstention as a valid controlled outcome.
11. Do not claim demographic fairness from operational slices.
12. Do not log raw user-entered narratives in the public demo.
13. Never place secrets in browser-visible `VITE_*` variables.
14. Stop and request a decision before changing the data target, taxonomy, security boundary, retention policy, model-selection rule, abstention policy, or public claim.

## Phase gates

The following require explicit user approval before implementation moves forward:

- final modelling population and date window;
- target taxonomy and taxonomy versioning strategy;
- temporal split boundaries;
- model-selection utility rule;
- operational abstention threshold;
- public input-retention behavior;
- deployment provider or paid service;
- API authentication design;
- promotion of any metric to README, portfolio, or resume;
- transition from one major phase in `SPEC.md` to the next.

## Code quality

- Prefer small, typed, testable modules.
- Keep notebooks exploratory; production behavior belongs in packages and commands.
- Use deterministic fixtures instead of live network calls in tests.
- Use structured error types and avoid exposing internal stack traces through APIs.
- Avoid premature infrastructure such as Kubernetes, distributed orchestration, or a feature store.
- Optimize for a clean local path before cloud deployment.

## Learning requirement

After each completed issue, append a short entry to `docs/learning_log.md` covering:

1. what the agent generated;
2. how the user can verify it;
3. what can fail in production; and
4. what the user should be able to explain in an interview.

Do not write an entry that claims the user reviewed or understood something unless they confirm it. Use a clearly marked draft when necessary.

