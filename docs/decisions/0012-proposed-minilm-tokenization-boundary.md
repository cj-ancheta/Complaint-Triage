# ADR 0012: Proposed MiniLM tokenization boundary

- Status: Accepted
- Date: 2026-07-23
- Decision owner: Charles Jr Ancheta
- Scope: CT-301 training-only tokenizer and truncation profile

## Context

Phase 3 needs a compact English encoder that can be fine-tuned on the local
Windows workstation. The workstation has an NVIDIA RTX 5060 Laptop GPU with
8,151 MiB of reported VRAM. The accepted analytical split contains 394,564
training rows, 80,992 validation rows, and 85,786 frozen test rows.

The repository's ordinary `.venv` uses Python 3.13. Current PyTorch Windows
installation guidance supports Python 3.9 through 3.12, so reusing that
environment would put the training path outside its documented support range.
The transformer environment and downloaded model files are local artifacts and
must not enter Git.

CT-301 must quantify truncation before selecting a maximum sequence length. It
must not use validation outcomes to choose an input boundary and must not train
a classifier.

## Proposed decision

Use `microsoft/MiniLM-L12-H384-uncased` as the initial compact encoder family.
Pin the immutable Hugging Face revision
`9a201d7b3ebebc5feabf9fbb4b3a4ec5d3f2440d`. Load weights only from the
revision's `model.safetensors` file when CT-303 begins; do not load its legacy
pickle-based `pytorch_model.bin`.

MiniLM is proposed because its official configuration has 12 layers, a hidden
size of 384, and a 512-position limit, while its model card reports 33 million
parameters. That is a more practical first candidate for 8 GiB VRAM than the
67-million-parameter DistilBERT reference. DeBERTa-v3-small is not the first
candidate because its 128,000-token vocabulary adds a large embedding table.
This is a resource-aware starting point, not a claim that MiniLM is more
accurate.

Create an ignored `.venv-transformer` with Python 3.12. Keep the ordinary
`.venv` unchanged. Pin the resolved transformer training environment in a
machine-readable requirements file before training; do not silently inherit
packages from the ordinary environment.

## CT-301 measurement contract

Tokenize complaint narrative text from the `train` partition only with the
pinned MiniLM tokenizer. Do not query, tokenize, count, or summarize validation
or test narratives. Include the tokenizer's normal special tokens and disable
truncation while measuring source lengths.

Evaluate the fixed candidate maximum lengths 128, 256, 384, and 512. The
commit-safe report may contain only:

- row counts and class-level aggregate counts;
- token-length minimum, maximum, mean, and fixed quantiles;
- for each candidate, counts and shares exceeding the boundary;
- aggregate retained-token ratios;
- the same measurements by product class; and
- immutable tokenizer identity, software versions, timing, and split lineage.

The report must not contain narratives, complaint identifiers, token IDs,
decoded tokens, vocabulary entries, row-level lengths, or row identities.
Downloaded tokenizer/model cache files remain ignored local artifacts governed
by ADR 0009.

CT-301 will not automatically choose a sequence length. It will present the
aggregate trade-off and stop for an explicit owner decision. This avoids hiding
a cost-versus-context judgment inside code. CT-302 may then enforce the accepted
length in the dataset pipeline.

## Accepted maximum length

The authoritative CT-301 report processed all 394,564 training narratives and
selected a maximum sequence length of **384 tokens** after owner review. No
validation or test narratives were accessed.

| Maximum length | Narratives exceeding boundary | Tokens retained |
|---:|---:|---:|
| 128 | 66.2841% | 37.8252% |
| 256 | 37.2855% | 60.1767% |
| **384** | **20.6742%** | **72.6368%** |
| 512 | 12.6968% | 79.8203% |

The training distribution has p75 343 tokens, p90 587, p95 813, and p99 1,828.
Moving from 256 to 384 retains another 12.4601 percentage points of tokens and
fully preserves 65,542 additional narratives. Moving from 384 to 512 retains a
smaller additional 7.1835 percentage points while increasing the maximum
attention-matrix dimension from 384 to 512. The latter is a 1.78-times increase
in maximum attention-score cells, although actual training cost will also
depend on dynamic padding, length grouping, batch size, and implementation.

At 384, Mortgage is the most affected class: 31.5508% of its training
narratives exceed the boundary and 66.9487% of its tokens are retained. Later
validation analysis must report the fixed long/truncated slice and must not
describe this operational slice as demographic fairness evidence.

## Reproducibility and failure behavior

- Verify the split manifest, run identity, taxonomy, and expected training
  count before reading narratives.
- Read only rows assigned to `train` by the accepted split materialization.
- Process text in bounded batches; never accumulate all narratives or token ID
  sequences in memory.
- Pin the model revision and reject mutable or mismatched revisions.
- Fail closed on missing narratives, unexpected labels, count drift, unsafe
  output paths, schema errors, or evidence conflicts.
- Make report publication atomic and idempotent.
- Keep the test access counter at zero.

## Alternatives considered

### DistilBERT base uncased

It has a mature model card and 512-position input boundary, but its reported 67
million parameters increase optimizer and activation pressure relative to
MiniLM. It remains a reasonable fallback if MiniLM integration fails.

### DeBERTa-v3-small

Its encoder is compact, but the official model card notes that the 128,000-token
vocabulary contributes 98 million embedding parameters. That makes the name
"small" misleading for this workstation's training-memory constraint.

### Python 3.13 in the ordinary environment

Rejected for the transformer training path because it is outside current
documented PyTorch Windows support. Keeping a separate Python 3.12 environment
also isolates the large CUDA stack from the baseline environment.

## Consequences and limitations

The immutable revision and safetensors requirement reduce supply-chain and
reproducibility risk. The separate environment costs disk space and adds one
setup step. Token-length evidence describes input retention, not predictive
quality, and therefore cannot establish that a longer context improves the
classifier. The final operational model still follows the later written utility
decision and may remain the TF-IDF baseline.

## Approval

Charles explicitly approved the MiniLM family and pinned revision, isolated
Python 3.12 environment, training-only aggregate measurement boundary, and
explicit post-report sequence-length decision gate on 2026-07-23. After
reviewing the aggregate profile, Charles approved 384 tokens as the CT-302
maximum sequence length on 2026-07-23.

## Primary references

- Microsoft MiniLM model card:
  <https://huggingface.co/microsoft/MiniLM-L12-H384-uncased>
- Pinned MiniLM revision:
  <https://huggingface.co/microsoft/MiniLM-L12-H384-uncased/tree/9a201d7b3ebebc5feabf9fbb4b3a4ec5d3f2440d>
- PyTorch Windows installation guidance:
  <https://docs.pytorch.org/get-started/locally/>
- Hugging Face padding and truncation guidance:
  <https://huggingface.co/docs/transformers/v5.0.0/pad_truncation>
