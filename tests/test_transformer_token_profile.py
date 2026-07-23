from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from complaint_triage.taxonomy import CURRENT_PRODUCT_LABELS
from complaint_triage.transformer_token_profile import (
    CANDIDATE_LENGTHS,
    MODEL_MAX_POSITIONS,
    MODEL_REVISION,
    LengthHistogram,
    TokenizerBundle,
    TransformerTokenProfileError,
    profile_training_rows,
    profile_transformer_tokens,
    safe_transformer_token_profile_error,
)


class FakeTokenizer:
    is_fast = True
    vocab_size = 30_522

    def __call__(self, texts, **kwargs):
        assert kwargs == {
            "add_special_tokens": True,
            "padding": False,
            "truncation": False,
            "return_attention_mask": False,
            "return_token_type_ids": False,
            "verbose": False,
        }
        return {"input_ids": [[101, *range(len(text.split())), 102] for text in texts]}

    def num_special_tokens_to_add(self, *, pair):
        assert pair is False
        return 2


def _bundle() -> TokenizerBundle:
    return TokenizerBundle(
        tokenizer=FakeTokenizer(),
        tokenizer_class="FakeTokenizer",
        config_class="FakeConfig",
        max_position_embeddings=MODEL_MAX_POSITIONS,
        hidden_size=384,
        hidden_layers=12,
    )


def _software() -> dict[str, str]:
    return {
        "python": "3.12.10",
        "transformers": "5.14.1",
        "tokenizers": "0.22.2",
        "huggingface_hub": "1.24.0",
    }


def _small_manifest_root(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    source_root = Path(__file__).parents[1]
    source = next((source_root / "data" / "manifests" / "cfpb" / "splits").glob("*.json"))
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest["class_counts_by_split"]["train"] = {label: 1 for label in CURRENT_PRODUCT_LABELS}
    manifest["split_counts"]["train"] = len(CURRENT_PRODUCT_LABELS)
    destination = tmp_path / "data" / "manifests" / "cfpb" / "splits" / source.name
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(manifest), encoding="utf-8")
    return destination, manifest


def test_length_histogram_uses_exact_nearest_rank_and_fixed_candidates() -> None:
    histogram = LengthHistogram()
    for length in (2, 4, 10, 130):
        histogram.add(length)

    report = histogram.as_report()

    assert report["record_count"] == 4
    assert report["token_count"] == 146
    assert report["quantiles"] == {"p50": 4, "p75": 10, "p90": 130, "p95": 130, "p99": 130}
    assert [item["maximum_length"] for item in report["candidate_lengths"]] == list(
        CANDIDATE_LENGTHS
    )
    assert report["candidate_lengths"][0] == {
        "maximum_length": 128,
        "records_exceeding": 1,
        "share_records_exceeding": 0.25,
        "retained_token_ratio": 0.986301,
    }


def test_training_profile_batches_without_retaining_tokens_or_rows() -> None:
    labels = tuple(sorted(CURRENT_PRODUCT_LABELS))
    rows = [(f"synthetic words class {index}", label) for index, label in enumerate(labels)]

    overall, by_class = profile_training_rows(
        rows,
        FakeTokenizer(),
        expected_counts={label: 1 for label in labels},
    )

    assert overall.record_count == 11
    assert overall.minimum == 6
    assert overall.maximum == 6
    assert all(value.record_count == 1 for value in by_class.values())


def test_training_profile_fails_closed_on_count_drift() -> None:
    labels = tuple(sorted(CURRENT_PRODUCT_LABELS))

    with pytest.raises(
        TransformerTokenProfileError, match="token_profile_source_counts_do_not_reconcile"
    ):
        profile_training_rows(
            [("synthetic complaint", labels[0])],
            FakeTokenizer(),
            expected_counts={label: 1 for label in labels},
        )


def test_full_synthetic_run_writes_closed_aggregate_report_and_replays(
    tmp_path: Path,
) -> None:
    split_path, _ = _small_manifest_root(tmp_path)
    labels = tuple(sorted(CURRENT_PRODUCT_LABELS))
    rows = [(f"private synthetic marker {index}", label) for index, label in enumerate(labels)]
    load_calls = 0

    def load_rows(manifest, settings):
        nonlocal load_calls
        load_calls += 1
        return iter(rows)

    report = profile_transformer_tokens(
        split_path,
        repository_root=tmp_path,
        settings=object(),
        lineage_reader=lambda root: ("a" * 40, True),
        clock=lambda: datetime(2026, 7, 23, 14, tzinfo=UTC),
        row_loader=load_rows,
        tokenizer_loader=lambda root: _bundle(),
        software_reader=_software,
    )

    encoded = json.dumps(report)
    assert "private synthetic marker" not in encoded
    assert MODEL_REVISION in encoded
    assert report["data"]["queried_splits"] == ["train"]
    assert report["data"]["validation_accessed"] is False
    assert report["data"]["test_accessed"] is False
    assert report["decision"]["maximum_length_selected"] is False
    assert report["privacy"]["contains_token_ids"] is False

    replay = profile_transformer_tokens(
        split_path,
        repository_root=tmp_path,
        settings=object(),
        lineage_reader=lambda root: ("b" * 40, False),
        row_loader=lambda manifest, settings: pytest.fail("replay reread source rows"),
        tokenizer_loader=lambda root: pytest.fail("replay reloaded tokenizer"),
        software_reader=_software,
    )
    assert replay == report
    assert load_calls == 1


def test_schema_and_query_exclude_sensitive_and_nontraining_data() -> None:
    root = Path(__file__).parents[1]
    schema = json.loads(
        (root / "contracts" / "cfpb-transformer-token-profile.schema.json").read_text(
            encoding="utf-8"
        )
    )
    source = (root / "src" / "complaint_triage" / "transformer_token_profile.py").read_text(
        encoding="utf-8"
    )

    assert schema["properties"]["privacy"]["properties"]["contains_narratives"] == {"const": False}
    assert schema["properties"]["privacy"]["properties"]["contains_token_ids"] == {"const": False}
    assert "o.split_assignment = 'train'" in source
    assert "o.split_assignment = ANY(%s)" not in source
    assert "model.safetensors" not in source


def test_safe_error_contains_no_source_values() -> None:
    output = safe_transformer_token_profile_error(
        TransformerTokenProfileError("token_profile_source_counts_do_not_reconcile")
    )

    assert output["error"] == {"code": "token_profile_source_counts_do_not_reconcile"}
    assert output["privacy"] == {
        "narratives_logged": False,
        "complaint_ids_logged": False,
        "token_ids_logged": False,
        "vocabulary_logged": False,
        "row_values_in_report": False,
    }
