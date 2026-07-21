# Controlled Vibe-Coding Workflow

## Operating loop

Every implementation issue follows:

```text
SPEC -> PLAN -> SMALL PATCH -> TEST -> EXPLAIN -> REVIEW -> COMMIT
```

The AI assistant may write most of the code. Charles retains ownership of product boundaries, model and data decisions, evidence, and public claims.

## Start of an issue

Use this prompt structure:

```text
Read SPEC.md and AGENTS.md completely, then inspect the files and tests relevant to issue <ID>.

Goal:
<one observable outcome>

Do not begin a later issue or phase.

Before editing:
1. Summarize current behavior.
2. State assumptions and risks.
3. Propose the smallest complete plan.
4. Identify how the result will be tested.

Then implement the change, add tests, run the relevant checks, and explain the diff. Do not commit. Suggest the next issue but do not start it.
```

## Review checkpoint

Before committing, Charles should be able to answer:

- What changed?
- Why is it needed?
- Which requirement does it implement?
- How was it tested?
- What can still fail?
- Did the data, API, security boundary, or public claims change?

Useful review commands:

```powershell
git status --short
git diff --stat
git diff
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
```

## Commit checkpoint

Commit only one coherent issue at a time. Suggested format:

```text
type(scope): observable outcome
```

Examples:

```text
chore(repo): establish tested Python project foundation
feat(source): add bounded CFPB metadata profiling
test(data): prevent duplicate records across temporal splits
docs(governance): define intended and prohibited model uses
```

The assistant must not create a commit unless Charles explicitly asks after reviewing the checkpoint.

## When to stop

Stop and ask for a decision when:

- the source schema differs from the specification;
- the taxonomy changes within the candidate date window;
- a new dependency or paid service is proposed;
- a change affects privacy, secrets, authentication, or data retention;
- a test exposes a mistaken requirement;
- a metric would be promoted publicly;
- a model threshold or deployment choice must be selected; or
- the next action crosses a phase gate in `AGENTS.md`.

## Recovery when generated code goes wrong

1. Do not stack more prompts on top of an unexplained failure.
2. Capture the exact command and error.
3. Ask the assistant to diagnose before editing.
4. Reduce the failing behavior to the smallest fixture.
5. Fix the root cause and add a regression test.
6. Re-run narrow checks, then full validation.
7. Review the diff before continuing.

Debug prompt:

```text
Diagnose this failure before changing code.

Expected behavior:
<expected>

Observed behavior:
<observed>

Reproduction command:
<command>

Error output:
<output>

Identify the most likely root cause and evidence. Propose the smallest fix and regression test. Do not edit tests unless the documented requirement is wrong.
```

