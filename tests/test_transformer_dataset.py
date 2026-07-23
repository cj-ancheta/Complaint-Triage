from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from complaint_triage.taxonomy import CURRENT_PRODUCT_LABELS
from complaint_triage.transformer_dataset import (
    ID_TO_LABEL,
    LABEL_TO_ID,
    LABELS,
    MAXIMUM_LENGTH,
    PAD_TO_MULTIPLE_OF,
    DatasetTokenizer,
    TransformerDatasetError,
    buffered_shuffle,
    collate_dynamic,
    safe_transformer_dataset_error,
    stream_tokenized_split,
    tokenize_rows,
    validate_transformer_dataset,
)
from complaint_triage.transformer_token_profile import TokenizerBundle


class FakeTokenizer:
    is_fast = True
    vocab_size = 30_522

    def __call__(self, texts, **kwargs):
        assert kwargs == {
            "add_special_tokens": True,
            "padding": False,
            "truncation": True,
            "max_length": MAXIMUM_LENGTH,
            "return_attention_mask": True,
            "return_token_type_ids": True,
            "verbose": False,
        }
        input_ids = []
        for text in texts:
            ids = [101, *[1_000 + index for index, _ in enumerate(text.split())], 102]
            input_ids.append(ids[:MAXIMUM_LENGTH])
        return {
            "input_ids": input_ids,
            "attention_mask": [[1] * len(ids) for ids in input_ids],
            "token_type_ids": [[0] * len(ids) for ids in input_ids],
        }

    def pad(self, features, **kwargs):
        assert kwargs == {
            "padding": True,
            "pad_to_multiple_of": PAD_TO_MULTIPLE_OF,
            "return_tensors": "np",
            "verbose": False,
        }
        longest = max(len(feature["input_ids"]) for feature in features)
        padded_length = ((longest + PAD_TO_MULTIPLE_OF - 1) // PAD_TO_MULTIPLE_OF) * 8

        def padded(key, pad_value):
            return np.asarray(
                [
                    list(feature[key]) + [pad_value] * (padded_length - len(feature[key]))
                    for feature in features
                ],
                dtype=np.int64,
            )

        return {
            "input_ids": padded("input_ids", 0),
            "attention_mask": padded("attention_mask", 0),
            "token_type_ids": padded("token_type_ids", 0),
            "labels": np.asarray([feature["labels"] for feature in features], dtype=np.int64),
        }


def _bundle(tokenizer: DatasetTokenizer | None = None) -> TokenizerBundle:
    return TokenizerBundle(
        tokenizer=tokenizer or FakeTokenizer(),
        tokenizer_class="FakeTokenizer",
        config_class="FakeConfig",
        max_position_embeddings=512,
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
    for split in ("train", "validation"):
        manifest["class_counts_by_split"][split] = {label: 1 for label in CURRENT_PRODUCT_LABELS}
        manifest["split_counts"][split] = len(CURRENT_PRODUCT_LABELS)
    destination = tmp_path / "data" / "manifests" / "cfpb" / "splits" / source.name
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(manifest), encoding="utf-8")
    return destination, manifest


def test_label_mapping_is_stable_alphabetical_and_bijective() -> None:
    assert LABELS == tuple(sorted(CURRENT_PRODUCT_LABELS))
    assert list(LABEL_TO_ID.values()) == list(range(11))
    assert {index: label for label, index in LABEL_TO_ID.items()} == ID_TO_LABEL


def test_tokenization_truncates_without_padding_or_raw_text() -> None:
    long_text = " ".join(f"word{index}" for index in range(500))

    features = list(tokenize_rows([(long_text, LABELS[0])], FakeTokenizer()))

    assert len(features) == 1
    assert set(features[0]) == {"input_ids", "attention_mask", "token_type_ids", "labels"}
    assert len(features[0]["input_ids"]) == MAXIMUM_LENGTH
    assert features[0]["attention_mask"] == [1] * MAXIMUM_LENGTH
    assert features[0]["labels"] == 0
    assert long_text not in json.dumps(features)


def test_dynamic_collation_pads_to_batch_longest_multiple_of_eight() -> None:
    tokenizer = FakeTokenizer()
    features = list(
        tokenize_rows(
            [("short text", LABELS[0]), ("this is a somewhat longer example", LABELS[1])],
            tokenizer,
        )
    )

    batch = collate_dynamic(features, tokenizer, return_tensors="np")

    assert batch["input_ids"].shape == (2, 8)
    assert batch["attention_mask"].shape == (2, 8)
    assert batch["labels"].shape == (2,)
    assert batch["attention_mask"][0].tolist() == [1, 1, 1, 1, 0, 0, 0, 0]


def test_buffered_shuffle_is_repeatable_epoch_sensitive_and_lossless() -> None:
    source = list(range(100))
    first = list(buffered_shuffle(source, buffer_size=8, seed=42))
    replay = list(buffered_shuffle(source, buffer_size=8, seed=42))
    next_epoch = list(buffered_shuffle(source, buffer_size=8, seed=43))

    assert first == replay
    assert first != next_epoch
    assert sorted(first) == source
    assert len(set(first)) == len(source)


def test_stream_rejects_test_before_calling_row_loader() -> None:
    with pytest.raises(TransformerDatasetError, match="transformer_dataset_split_forbidden"):
        list(
            stream_tokenized_split(
                {},
                object(),
                "test",
                FakeTokenizer(),
                row_loader=lambda *args: pytest.fail("forbidden split reached the row loader"),
            )
        )


def test_validation_shuffle_is_forbidden() -> None:
    with pytest.raises(
        TransformerDatasetError, match="transformer_dataset_validation_shuffle_forbidden"
    ):
        list(
            stream_tokenized_split(
                {},
                object(),
                "validation",
                FakeTokenizer(),
                epoch=0,
                row_loader=lambda *args: [],
            )
        )


def test_training_epoch_shuffle_uses_stable_seed_and_preserves_labels() -> None:
    rows = [(f"unique{index}", LABELS[index % len(LABELS)]) for index in range(100)]

    def loader(manifest, settings, split):
        assert split == "train"
        return iter(rows)

    first = list(
        stream_tokenized_split({}, object(), "train", FakeTokenizer(), epoch=0, row_loader=loader)
    )
    replay = list(
        stream_tokenized_split({}, object(), "train", FakeTokenizer(), epoch=0, row_loader=loader)
    )
    second = list(
        stream_tokenized_split({}, object(), "train", FakeTokenizer(), epoch=1, row_loader=loader)
    )

    assert first == replay
    assert first != second
    assert sorted(item["labels"] for item in first) == sorted(
        LABEL_TO_ID[label] for _, label in rows
    )


def test_full_synthetic_validation_writes_closed_report_and_replays(tmp_path: Path) -> None:
    split_path, _ = _small_manifest_root(tmp_path)
    rows_by_split = {
        split: [(f"private {split} marker {index}", label) for index, label in enumerate(LABELS)]
        for split in ("train", "validation")
    }
    load_calls: list[str] = []

    def loader(manifest, settings, split):
        load_calls.append(split)
        return iter(rows_by_split[split])

    report = validate_transformer_dataset(
        split_path,
        repository_root=tmp_path,
        settings=object(),
        lineage_reader=lambda root: ("a" * 40, True),
        clock=lambda: datetime(2026, 7, 24, 1, tzinfo=UTC),
        row_loader=loader,
        tokenizer_loader=lambda root: _bundle(),
        software_reader=_software,
    )

    encoded = json.dumps(report)
    assert "private train marker" not in encoded
    assert "private validation marker" not in encoded
    assert report["data"]["queried_splits"] == ["train", "validation"]
    assert report["data"]["test_accessed"] is False
    assert report["pipeline"]["maximum_length"] == 384
    assert report["splits"]["train"]["record_count"] == 11
    assert report["splits"]["validation"]["record_count"] == 11
    assert report["privacy"]["tokenized_dataset_persisted"] is False

    replay = validate_transformer_dataset(
        split_path,
        repository_root=tmp_path,
        settings=object(),
        lineage_reader=lambda root: ("b" * 40, False),
        row_loader=lambda *args: pytest.fail("replay reread rows"),
        tokenizer_loader=lambda root: pytest.fail("replay reloaded tokenizer"),
        software_reader=_software,
    )
    assert replay == report
    assert load_calls == ["train", "validation"]


def test_schema_and_query_exclude_test_and_sensitive_values() -> None:
    root = Path(__file__).parents[1]
    schema = json.loads(
        (root / "contracts" / "cfpb-transformer-dataset.schema.json").read_text(encoding="utf-8")
    )
    source = (root / "src" / "complaint_triage" / "transformer_dataset.py").read_text(
        encoding="utf-8"
    )

    assert schema["properties"]["data"]["properties"]["allowed_splits"] == {
        "const": ["train", "validation"]
    }
    assert schema["properties"]["privacy"]["properties"]["contains_narratives"] == {"const": False}
    assert "o.split_assignment = %s" in source
    assert "o.split_assignment = 'test'" not in source


def test_safe_error_contains_no_source_values() -> None:
    output = safe_transformer_dataset_error(
        TransformerDatasetError("transformer_dataset_source_counts_do_not_reconcile")
    )

    assert output["error"] == {"code": "transformer_dataset_source_counts_do_not_reconcile"}
    assert output["privacy"] == {
        "narratives_logged": False,
        "complaint_ids_logged": False,
        "token_ids_logged": False,
        "row_values_in_report": False,
    }
