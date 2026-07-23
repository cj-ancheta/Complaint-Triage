# Training-only transformer token profile

CT-301 measures how much of the accepted training narratives fit within four
candidate MiniLM sequence lengths. It does not train a classifier, read
validation rows, touch the frozen test partition, or report predictive metrics.

## Why this comes before training

Transformer memory and runtime grow with sequence length. Choosing 512 simply
because the model permits it would spend substantially more compute without
first showing how much additional complaint text it retains. The profile makes
that trade-off visible using input evidence that cannot optimize against
validation labels.

The report uses the pinned tokenizer from ADR 0012 and counts its normal special
tokens. Each narrative is tokenized without truncation or padding. Exact
nearest-rank quantiles are derived from aggregate length histograms. No token ID
sequence or row-level length is persisted.

## Isolated setup

The existing `.venv` remains the baseline environment. CT-301 uses Python 3.12
because current PyTorch Windows guidance does not list Python 3.13 as supported.
PyTorch itself is not installed until the later training issue.

```powershell
winget install --id Python.Python.3.12 --exact --scope user
py -3.12 -m venv .venv-transformer
.\.venv-transformer\Scripts\python.exe -m pip install --upgrade pip
.\.venv-transformer\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv-transformer\Scripts\python.exe -m pip install `
  -r requirements-transformer-tokenizer.txt
```

Both `.venv-transformer/` and `data/model_cache/` are ignored. The cache contains
the public upstream tokenizer vocabulary, not complaint narratives, but it is
kept local to preserve the pinned dependency boundary and avoid committing
downloaded artifacts.

## Run

The first authoritative report requires a clean implementation commit:

```powershell
.\.venv-transformer\Scripts\complaint-triage.exe `
  profile-transformer-tokens `
  --split-manifest `
  data/manifests/cfpb/splits/cfpb-run-20260722T130728Z-2b7815d4c850-split-1.0.0.json
```

The report is written under `data/evaluations/cfpb/tokenizer-profile/`. An
idempotent replay validates and returns the existing report without rereading
the database.

## Interpret

For 128, 256, 384, and 512 tokens, inspect both:

- `share_records_exceeding`: the share of narratives that lose at least one
  token; and
- `retained_token_ratio`: the share of all measured tokens retained after the
  boundary is applied.

Review overall and per-class values together. A low overall truncation rate can
hide concentrated information loss in a rare route. These are input-retention
statistics, not evidence that longer input improves model quality.

CT-301 stops after presenting this evidence. Charles selects the maximum length
before CT-302 makes it a dataset-pipeline invariant.

## Verify

```powershell
.\.venv-transformer\Scripts\ruff.exe check .
.\.venv-transformer\Scripts\ruff.exe format --check .
.\.venv-transformer\Scripts\pytest.exe -q
```

The tests use a deterministic fake tokenizer and synthetic narratives. They do
not call Hugging Face or the live CFPB source.
