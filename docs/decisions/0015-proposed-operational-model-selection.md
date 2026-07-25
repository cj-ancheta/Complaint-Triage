# ADR 0015: Proposed operational model-selection utility rule

- Status: Accepted
- Date: 2026-07-25
- Decision owner: Charles Jr Ancheta
- Scope: CT-306 validation-only baseline-versus-transformer operational decision

## Context

CT-304 compared the accepted TF-IDF logistic-regression candidate with the
accepted epoch-3 MiniLM candidate on the same 80,992 validation rows. MiniLM
improved validation macro F1 by `0.0360851057`, weighted F1 by `0.0074011404`,
accuracy by `0.0021609237`, and worst-class recall by `0.1497794581`. It had
higher class F1 for ten of eleven labels, but its retained weights were
`6.801287` times larger. These are validation results and are not yet approved
as public portfolio claims.

CT-305 fitted one scalar temperature on September 2024 validation logits and
assessed it on October 2024 validation logits. The calibrated candidate passed
all predeclared eligibility checks: October negative log-likelihood, Brier
loss, and both recorded top-label ECE estimates improved while argmax and top-2
membership remained unchanged. Class-specific calibration remained mixed.

Neither issue measured comparable CPU serving latency or process memory. The
project also has not yet made a written trade-off across explainability,
operational complexity, and deployment cost. CT-306 must declare that rule
before running the operational benchmark so its limits cannot be adjusted to
favor the observed winner.

## Deployment scenario

The decision is for the first public portfolio demonstration, not for an
unbounded production workload. The service must:

- process one complaint narrative per request;
- run inference on CPU after a one-time process and model load;
- require no GPU, network call, or paid inference API;
- support a small reviewer-facing demonstration rather than bulk scoring;
- return calibrated probabilities if MiniLM is selected; and
- retain human review and later abstention as separate policy controls.

Selecting a hosting provider, public input-retention policy, API authentication
design, and operational abstention threshold remain separate phase gates.

## Decision method

Use a gated rule rather than a weighted score. A weighted score would introduce
arbitrary exchange rates between rare-class quality, milliseconds, memory, and
explainability. Calibrated MiniLM is selected only if it passes every gate
below. If any gate fails or cannot be verified, select the accepted TF-IDF
logistic-regression pipeline.

### Gate 1: evidence and lineage

Both candidates and every source report must reproduce their accepted hashes,
row counts, ordered labels, feature boundary, and untouched-test declarations.
The benchmark implementation must be committed and the worktree clean before a
real-data run. The frozen test partition must not be queried or scored.

### Gate 2: material validation quality

Relative to TF-IDF, MiniLM must satisfy all of these requirements on the
already accepted CT-304 evidence:

- macro-F1 improvement of at least `0.020`;
- worst-class-recall improvement of at least `0.050`;
- no decrease in validation accuracy;
- no decrease in validation weighted F1; and
- no more than one of the eleven classes with lower class F1.

Macro F1 and worst-class recall receive explicit floors because the training
population is highly imbalanced and aggregate accuracy is dominated by the
largest label. The rule does not require every class to improve because a
single compact model can involve a small local trade-off.

### Gate 3: probability calibration

MiniLM must remain eligible under the accepted ADR 0014 calibration rule. The
temperature artifact and calibration report must reproduce their accepted
hashes. October negative log-likelihood must be lower after scaling, October
multiclass Brier loss must stay within its accepted guard, probabilities must
remain valid, and rankings must remain unchanged.

The class-specific calibration limitation must be carried into the model card.
Passing this gate does not authorize an abstention threshold.

### Gate 4: CPU service usability

On the declared reference machine and benchmark below, calibrated MiniLM must
satisfy all of these absolute ceilings:

- warmed single-narrative end-to-end p95 latency no greater than `750 ms`;
- maximum warmed single-narrative latency no greater than `1,500 ms`;
- one-time model-and-tokenizer load no greater than `30 seconds`;
- peak process working set no greater than `2 GiB`; and
- retained model plus calibration artifacts no greater than `256 MiB`.

The absolute ceilings represent an interactive, low-volume reviewer demo. The
report must also show TF-IDF-to-MiniLM latency, memory, load-time, and artifact
ratios, but those relative ratios are diagnostic rather than gates: a very fast
sparse baseline can make a usable transformer look disproportionately slower.

Passing on the reference laptop does not claim identical cloud performance.
The selected deployment provider must be benchmarked separately before public
deployment.

### Gate 5: explainability boundary

MiniLM is eligible only if the operational documentation:

- uses global and per-class validation evidence and example-based error
  analysis rather than presenting attention weights as reasoning;
- describes confidence as a calibrated model estimate, not a business
  justification or probability that a complaint is true;
- labels top alternatives as model outputs rather than causal explanations;
- documents the class-specific calibration limitation; and
- does not generate purported local reason codes from unvalidated transformer
  internals.

TF-IDF coefficients remain easier to inspect, but that advantage is not treated
as an automatic veto when the quality, calibration, and usability gates pass.
Any later reason-code feature needs its own transparent contract and tests.

### Gate 6: complexity and cost boundary

MiniLM is eligible only if the first service can use the existing pinned local
PyTorch, Transformers, tokenizer, and safetensors boundary without:

- a required GPU;
- an external model or LLM request;
- a paid inference service;
- Kubernetes or distributed orchestration; or
- a second operational model for the same routing decision.

The report must record the larger dependency, image, cold-start, and maintenance
surface as a cost. This extra complexity is accepted only when Gates 1 through
5 demonstrate material quality and usable CPU operation. Actual provider price
cannot be claimed until a provider is separately approved.

## Fixed CPU benchmark contract

### Reference environment

The first run is bound to the current laptop:

- CPU: Intel Core Ultra 7 255HX, 20 cores and 20 logical processors;
- physical memory: 33,752,997,888 bytes;
- operating system, Python version, library versions, process architecture,
  thread settings, and power-state caveats recorded at runtime; and
- GPU disabled and unavailable to both candidates for the benchmark.

The transformer process uses four PyTorch intra-operation threads and one
inter-operation thread. Thread counts are fixed before inference and recorded.
The report must warn that laptop power and thermal behavior can affect timings.

### Validation-only workload

Use only included October 2024 validation narratives from the accepted run,
population, split, and taxonomy versions. Select the 512 rows with the lowest
accepted normalized-narrative fingerprint values. A cryptographic fingerprint
ordering gives a deterministic population-proportional sample without tuning
the selection by label, length, or model outcome.

Keep narratives, labels, fingerprints, row identities, tokens, sparse vectors,
and per-row timings in memory only. Persist no row-level information. The
commit-safe report may contain only aggregate counts, aggregate narrative-length
statistics, timings, memory, ratios, hashes, environment metadata, gate results,
and the final decision.

### Measurement procedure

Run each candidate in a fresh subprocess so one model's allocations cannot
inflate the other's memory result.

For each candidate:

1. verify all governed input report and artifact hashes;
2. disable network access through the existing offline model-loading boundary;
3. load the complete prediction pipeline and record wall-clock load time;
4. run the first 16 selected narratives once as an unmeasured warm-up;
5. score all 512 narratives individually for three measured passes in the same
   fixed order;
6. include candidate-specific preprocessing, model inference, probability
   calculation, and MiniLM temperature scaling in each timing;
7. synchronize before stopping a timing if the runtime exposes asynchronous
   work;
8. record p50, p95, maximum, arithmetic mean, and measured-prediction count from
   `1,536` observations; and
9. record process peak working set after loading and inference.

Use a monotonic high-resolution clock. Do not include database retrieval,
process startup, report serialization, or model load in warmed request latency;
those costs are recorded separately. Do not batch multiple narratives into one
model call. Validate that both candidates return the expected eleven-label
probability contract for every measured call, but do not publish prediction
quality from this benchmark sample.

On Windows, obtain current and peak process working set through the operating
system process-memory API using the standard library. On another operating
system, the implementation must provide an explicitly reviewed equivalent or
fail closed. No new runtime dependency is approved by this proposal.

### Closed report and replay

Write one versioned aggregate report under
`data/evaluations/cfpb/model-selection/`. It must contain:

- source report and artifact hashes;
- workload contract and reconciled counts;
- reference environment and fixed thread configuration;
- per-candidate load time, latency summaries, peak working set, artifact bytes,
  and safe ratios;
- the accepted quality and calibration evidence needed by the gates;
- the explainability, complexity, and cost assessment;
- every gate result and its supporting value;
- `test_accessed=false`;
- `operational_threshold_selected=false`;
- `portfolio_promotion_approved=false`; and
- exactly one final operational model when every report check succeeds.

Use atomic writes. An identical replay validates and returns the existing
report unchanged. Changed source bytes, missing local artifacts, unsafe paths,
sample-count drift, a prediction-contract failure, non-finite values, or an
unsupported memory-measurement platform must fail closed without a partial
report or model decision.

## Result interpretation

If calibrated MiniLM passes all six gates, CT-306 selects calibrated MiniLM as
the operational candidate for the later abstention, test, API, and governance
phases. If any gate fails, CT-306 selects TF-IDF logistic regression and records
the exact failed gate. Selection does not authorize final test access, a public
metric, an abstention threshold, deployment, or a production claim.

## Consequences

This rule gives rare-class quality and calibrated confidence meaningful weight
while enforcing an interactive CPU boundary. It accepts that the transformer
is less directly interpretable and more complex, but only when its measured
quality improvement is material and it remains practical for the intended
demo. The fallback is a complete accepted model rather than a failed project.

The 512-row, three-pass benchmark reduces timing noise but is still one laptop
measurement. It does not represent concurrency, tail latency under load,
container cold starts, cloud throttling, or ongoing provider cost. Those remain
service and deployment evidence.

## Approval

Charles approved the following CT-306 boundary on 2026-07-25:

- the six-gate decision method and TF-IDF fallback;
- the quality floors;
- the CPU latency, load-time, memory, and artifact ceilings;
- the deterministic 512-row validation-only workload and three-pass procedure;
- the explainability and no-paid-service boundaries; and
- the continued prohibition on test access, threshold selection, deployment,
  and public metric promotion.

The approval was recorded before the CPU benchmark implementation or real-data
timing run. Selective accuracy remains covered as an explicitly deferred
dimension because CT-306 selects the candidate model before Phase 4 declares
and evaluates an abstention policy.
