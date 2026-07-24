import json
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest

import complaint_triage.transformer_calibration as transformer_calibration
from complaint_triage.transformer_calibration import (
    EXPECTED_PARTITION_CLASS_COUNTS,
    LABELS,
    CalibrationInference,
    TransformerCalibrationError,
    _partition_for_date,
    calibrate_transformer,
    calibration_metrics,
    equal_width_reliability,
    fit_temperature,
    probabilities_from_logits,
    safe_transformer_calibration_error,
)
from complaint_triage.transformer_dataset import PAD_TO_MULTIPLE_OF, stream_collated_batches


class FakeTokenizer:
    def __call__(self, texts, **kwargs):
        input_ids = [[101, *range(1000, 1000 + len(text.split())), 102] for text in texts]
        return {
            "input_ids": input_ids,
            "attention_mask": [[1] * len(ids) for ids in input_ids],
            "token_type_ids": [[0] * len(ids) for ids in input_ids],
        }

    def pad(self, features, **kwargs):
        longest = max(len(feature["input_ids"]) for feature in features)
        width = ((longest + PAD_TO_MULTIPLE_OF - 1) // PAD_TO_MULTIPLE_OF) * PAD_TO_MULTIPLE_OF

        def padded(key, value):
            return np.asarray(
                [list(item[key]) + [value] * (width - len(item[key])) for item in features]
            )

        return {
            "input_ids": padded("input_ids", 0),
            "attention_mask": padded("attention_mask", 0),
            "token_type_ids": padded("token_type_ids", 0),
            "labels": np.asarray([item["labels"] for item in features]),
        }


def _overconfident_fixture() -> tuple[np.ndarray, np.ndarray]:
    labels = np.arange(220, dtype=np.int64) % len(LABELS)
    logits = np.zeros((labels.size, len(LABELS)), dtype=np.float64)
    predictions = labels.copy()
    predictions[::5] = (predictions[::5] + 1) % len(LABELS)
    logits[np.arange(labels.size), predictions] = 8.0
    return logits, labels


def test_temperature_fit_lowers_nll_and_preserves_rankings() -> None:
    logits, labels = _overconfident_fixture()

    fitted = fit_temperature(logits, labels)
    before = calibration_metrics(logits, labels, temperature=1.0)
    after = calibration_metrics(logits, labels, temperature=fitted["temperature"])
    before_probabilities = probabilities_from_logits(logits, temperature=1.0)
    after_probabilities = probabilities_from_logits(
        logits, temperature=float(fitted["temperature"])
    )

    assert fitted["temperature"] > 1.0
    assert after["negative_log_likelihood"] < before["negative_log_likelihood"]
    assert np.array_equal(before_probabilities.argmax(axis=1), after_probabilities.argmax(axis=1))
    assert np.allclose(after_probabilities.sum(axis=1), 1.0, atol=1e-12)


def test_reliability_bins_are_closed_and_reconcile() -> None:
    confidence = np.array([0.0, 0.2, 0.5, 0.999, 1.0])
    correct = np.array([False, True, True, False, True])

    bins = equal_width_reliability(confidence, correct, bin_count=15)

    assert len(bins) == 15
    assert sum(item["record_count"] for item in bins) == 5
    assert sum(item["correct_count"] for item in bins) == 3
    assert bins[0]["record_count"] == 1
    assert bins[-1]["record_count"] == 2
    assert bins[-1]["upper_inclusive"] == 1.0
    assert bins[-1]["upper_exclusive"] is None


@pytest.mark.parametrize(
    ("received", "expected"),
    [
        (date(2024, 9, 1), "calibration_fit"),
        (date(2024, 9, 30), "calibration_fit"),
        (date(2024, 10, 1), "calibration_evaluation"),
        (date(2024, 10, 31), "calibration_evaluation"),
    ],
)
def test_temporal_partition_boundaries(received: date, expected: str) -> None:
    assert _partition_for_date(received) == expected


@pytest.mark.parametrize("received", [date(2024, 8, 31), date(2024, 11, 1)])
def test_temporal_partition_rejects_dates_outside_validation(received: date) -> None:
    with pytest.raises(
        TransformerCalibrationError, match="transformer_calibration_date_outside_boundary"
    ):
        _partition_for_date(received)


def test_partition_metadata_preserves_canonical_batch_composition(monkeypatch) -> None:
    rows = [
        (
            " ".join(["word"] * (1 + index % 31)),
            LABELS[index % len(LABELS)],
            date(2024, 9 if index % 2 == 0 else 10, 1),
        )
        for index in range(1_050)
    ]
    tokenizer = FakeTokenizer()
    manifest = {"run_id": "synthetic"}
    monkeypatch.setattr(
        transformer_calibration,
        "iter_validation_rows",
        lambda manifest, settings: iter(rows),
    )

    partitioned = list(
        transformer_calibration._stream_partitioned_batches(
            manifest, object(), tokenizer, batch_size=16
        )
    )
    canonical = list(
        stream_collated_batches(
            manifest,
            object(),
            "validation",
            tokenizer,
            batch_size=16,
            return_tensors="pt",
            row_loader=lambda manifest, settings, split: iter(
                (narrative, label) for narrative, label, _ in rows
            ),
        )
    )

    assert len(partitioned) == len(canonical)
    for (actual, partitions), expected in zip(partitioned, canonical, strict=True):
        assert np.array_equal(actual["input_ids"], expected["input_ids"])
        assert np.array_equal(actual["labels"], expected["labels"])
        assert len(partitions) == len(expected["labels"])


def _copy_sources(root: Path) -> Path:
    source_root = Path(__file__).parents[1]
    for relative in (
        Path("data/evaluations/cfpb/transformer"),
        Path("data/evaluations/cfpb/model-comparison"),
        Path("data/manifests/cfpb/splits"),
    ):
        source = next((source_root / relative).glob("*.json"))
        destination = root / relative / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    return next((root / "data/evaluations/cfpb/transformer").glob("*.json"))


def _accepted_shape_inference() -> CalibrationInference:
    source_root = Path(__file__).parents[1]
    report = json.loads(
        next((source_root / "data/evaluations/cfpb/transformer").glob("*.json")).read_text(
            encoding="utf-8"
        )
    )
    selected = next(
        epoch
        for epoch in report["epochs"]
        if epoch["epoch"] == report["selection"]["selected_epoch"]
    )
    matrix = selected["validation"]["metrics"]["confusion_matrix"]["rows"]
    labels: list[int] = []
    predictions: list[int] = []
    partitions: list[str] = []
    for actual, row in enumerate(matrix):
        class_predictions = [predicted for predicted, count in enumerate(row) for _ in range(count)]
        fit_count = EXPECTED_PARTITION_CLASS_COUNTS["calibration_fit"][LABELS[actual]]
        labels.extend([actual] * len(class_predictions))
        predictions.extend(class_predictions)
        partitions.extend(
            ["calibration_fit"] * fit_count
            + ["calibration_evaluation"] * (len(class_predictions) - fit_count)
        )
    labels_array = np.asarray(labels, dtype=np.int64)
    predictions_array = np.asarray(predictions, dtype=np.int64)
    logits = np.zeros((labels_array.size, len(LABELS)), dtype=np.float64)
    logits[np.arange(labels_array.size), predictions_array] = 5.0
    correct = predictions_array == labels_array
    accepted_top2 = round(selected["validation"]["metrics"]["top_2_accuracy"] * labels_array.size)
    additional_top2 = accepted_top2 - int(correct.sum())
    error_indices = np.flatnonzero(~correct)
    top_2_correct = correct.copy()
    top_2_correct[error_indices[:additional_top2]] = True
    logits[error_indices[:additional_top2], labels_array[error_indices[:additional_top2]]] = 4.0
    for index in error_indices[additional_top2:]:
        distractor = next(
            value
            for value in range(len(LABELS))
            if value not in (labels_array[index], predictions_array[index])
        )
        logits[index, distractor] = 4.0
    return CalibrationInference(
        logits=logits,
        labels=labels_array,
        partitions=np.asarray(partitions, dtype="U24"),
        top_2_correct=top_2_correct,
        elapsed_seconds=12.5,
        peak_cuda_bytes=1234,
    )


def test_full_aggregate_report_validates_and_replays(tmp_path: Path) -> None:
    transformer_report = _copy_sources(tmp_path)
    inference = _accepted_shape_inference()
    verified: list[str] = []

    report = calibrate_transformer(
        transformer_report,
        repository_root=tmp_path,
        settings=object(),
        lineage_reader=lambda _: ("a" * 40, True),
        clock=lambda: datetime(2026, 7, 24, 13, tzinfo=UTC),
        artifact_verifier=lambda root, metadata: verified.append(metadata["sha256"]),
        inference_runner=lambda **kwargs: inference,
        software_reader=lambda: {
            "python": "3.12.10",
            "numpy": "2.5.1",
            "scipy": "1.18.0",
            "torch": "2.13.0+cu130",
            "transformers": "5.14.1",
            "safetensors": "0.8.0",
        },
    )

    assert verified
    assert report["data"]["test_accessed"] is False
    assert report["results"]["calibration_fit"]["before"]["record_count"] == 39_161
    assert report["results"]["calibration_evaluation"]["before"]["record_count"] == 41_831
    assert report["claims"]["operational_threshold_selected"] is False
    assert report["eligibility"]["final_operational_model_selected"] is False
    assert (tmp_path / report["artifact"]["relative_path"]).is_file()

    replay = calibrate_transformer(
        transformer_report,
        repository_root=tmp_path,
        lineage_reader=lambda _: ("b" * 40, False),
        artifact_verifier=lambda root, metadata: None,
    )
    assert replay == report


def test_safe_error_and_production_query_exclude_test_and_rows() -> None:
    result = safe_transformer_calibration_error(
        TransformerCalibrationError("transformer_calibration_source_identity_mismatch")
    )
    source = (
        Path(__file__).parents[1] / "src" / "complaint_triage" / "transformer_calibration.py"
    ).read_text(encoding="utf-8")

    assert result["privacy"]["narratives_logged"] is False
    assert "o.split_assignment = 'validation'" in source
    assert "o.split_assignment = 'test'" not in source
    assert "no_abstention_threshold_selected_in_ct305" in source
