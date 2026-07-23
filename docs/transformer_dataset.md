# Transformer dataset and tokenizer pipeline

CT-302 turns the accepted temporal split and 384-token boundary into a reusable
dataset contract. It validates data preparation only: no classifier is loaded,
trained, scored, calibrated, or compared.

## Contract

- Only `train` and `validation` are legal dataset splits. `test` fails before a
  database connection is opened.
- The eleven accepted product labels are sorted alphabetically and mapped
  bijectively to integer IDs 0 through 10.
- The pinned MiniLM tokenizer adds its normal special tokens, truncates to 384,
  and stores no padding in individual examples.
- A caller batch is padded dynamically to its longest example, rounded to a
  multiple of eight. The implementation intentionally omits `max_length` from
  the padding call because current Transformers ignores it with
  `padding=True`; every input is checked against 384 before padding.
- Canonical source order is stable. Training callers may request a bounded
  8,192-row shuffle using seed `42 + epoch`. Validation shuffling is forbidden.
- Shuffling changes order only. It does not resample or alter class frequency.
  The class-weighting or sampling decision belongs to CT-303.

The source is streamed from PostgreSQL and tokenized in 256-row batches. Raw
text, row identities, token arrays, and a materialized dataset are not written
to disk. This avoids creating another large governed copy of the narratives.

## Why dynamic padding

Padding every example to 384 would waste computation on short narratives.
Dynamic padding delays padding until the training caller has formed a batch and
pads only to that batch's longest sequence. Rounding to a multiple of eight is
compatible with common accelerator tensor dimensions while preserving the
approved 384 ceiling.

## Validate

After the implementation is committed, run from the isolated Python 3.12
environment:

```powershell
.\.venv-transformer\Scripts\complaint-triage.exe `
  validate-transformer-dataset `
  --split-manifest `
  data/manifests/cfpb/splits/cfpb-run-20260722T130728Z-2b7815d4c850-split-1.0.0.json
```

The command fully streams train and validation, reconciles every class count,
and tests dynamic collation in deterministic 32-example check batches. Its
commit-safe report contains only aggregate counts, lengths, configuration,
timing, software versions, and boolean checks.

An idempotent replay validates and returns the existing report without reading
the database or tokenizer again.

## Training integration

CT-303 can call `stream_tokenized_split(..., split="train", epoch=n)` to obtain
a reproducibly shuffled epoch and `stream_tokenized_split(...,
split="validation")` for stable validation. It can call `collate_dynamic` with
`return_tensors="pt"` after PyTorch is installed. CT-302 itself uses NumPy
tensors only for shape validation and does not install PyTorch.

## Limits

The bounded-buffer order is reproducible but is not a uniform global shuffle.
The initial pipeline is single-process; multi-worker or distributed partitioning
must not be enabled without adding explicit no-duplication tests. Padding shape
evidence from 32-example canonical check batches is a correctness check, not a
training-memory or throughput benchmark.

## Primary references

- Hugging Face padding and truncation:
  <https://huggingface.co/docs/transformers/en/pad_truncation>
- Hugging Face data collators:
  <https://huggingface.co/docs/transformers/en/main_classes/data_collator>
- Hugging Face tokenizer API:
  <https://huggingface.co/docs/transformers/en/main_classes/tokenizer>
