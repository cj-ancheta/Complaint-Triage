from __future__ import annotations

from pathlib import Path

import pytest

from complaint_triage.transformer_dataset import LABELS
from complaint_triage.transformer_training import (
    BATCH_CONFIGURATIONS,
    EFFECTIVE_BATCH_SIZE,
    MODEL_ID,
    MODEL_REVISION,
    BatchProbeOutOfMemory,
    TransformerTrainingError,
    _reconcile_smoke_rows,
    load_pinned_sequence_classifier,
    safe_transformer_training_error,
    select_batch_configuration,
    square_root_balanced_weights,
)


def _class_counts() -> dict[str, int]:
    return {
        "Checking or savings account": 27_501,
        "Credit card": 30_122,
        "Credit reporting or other personal consumer reports": 248_062,
        "Debt collection": 41_325,
        "Debt or credit management": 1_173,
        "Money transfer, virtual currency, or money service": 9_462,
        "Mortgage": 12_136,
        "Payday loan, title loan, personal loan, or advance loan": 4_751,
        "Prepaid card": 3_830,
        "Student loan": 9_150,
        "Vehicle loan or lease": 7_052,
    }


def test_square_root_weights_follow_approved_training_only_formula() -> None:
    weights = square_root_balanced_weights(_class_counts())

    assert len(weights) == 11
    assert weights[2] == pytest.approx(0.3803, abs=0.0001)
    assert weights[4] == pytest.approx(5.5299, abs=0.0001)
    assert weights[8] == pytest.approx(3.0603, abs=0.0001)
    assert max(weights) / min(weights) < 15


def test_batch_ladder_preserves_effective_batch_and_approved_order() -> None:
    assert [
        (
            item.per_device_batch_size,
            item.gradient_accumulation_steps,
            item.gradient_checkpointing,
        )
        for item in BATCH_CONFIGURATIONS
    ] == [(16, 2, False), (8, 4, False), (4, 8, True)]
    assert all(
        item.per_device_batch_size * item.gradient_accumulation_steps == EFFECTIVE_BATCH_SIZE
        for item in BATCH_CONFIGURATIONS
    )


def test_batch_selection_falls_back_only_on_memory_and_records_attempts() -> None:
    calls = []

    def probe(configuration):
        calls.append(configuration.per_device_batch_size)
        if configuration.per_device_batch_size == 16:
            raise BatchProbeOutOfMemory
        return {"peak_cuda_bytes": 123, "loss_finite": True}

    selected, result, attempts = select_batch_configuration(probe)

    assert calls == [16, 8]
    assert selected.per_device_batch_size == 8
    assert result["peak_cuda_bytes"] == 123
    assert [item["status"] for item in attempts] == ["cuda_out_of_memory", "passed"]


def test_batch_selection_fails_closed_when_every_configuration_ooms() -> None:
    def probe(configuration):
        raise BatchProbeOutOfMemory

    with pytest.raises(
        TransformerTrainingError, match="transformer_training_no_batch_configuration_fits"
    ):
        select_batch_configuration(probe)


def test_model_loader_pins_revision_and_requires_safetensors(tmp_path: Path) -> None:
    captured = {}

    class Config:
        _commit_hash = MODEL_REVISION

    class Model:
        config = Config()

    class AutoModel:
        @staticmethod
        def from_pretrained(model_id, **kwargs):
            captured["model_id"] = model_id
            captured.update(kwargs)
            return Model()

    model = load_pinned_sequence_classifier(tmp_path, auto_model_class=AutoModel)

    assert isinstance(model, Model)
    assert captured["model_id"] == MODEL_ID
    assert captured["revision"] == MODEL_REVISION
    assert captured["use_safetensors"] is True
    assert captured["trust_remote_code"] is False
    assert captured["num_labels"] == 11


def test_smoke_rows_must_reconcile_exactly_100_per_class() -> None:
    valid = [(f"synthetic {index}", label) for label in LABELS for index in range(100)]
    _reconcile_smoke_rows(valid)

    with pytest.raises(
        TransformerTrainingError, match="transformer_training_smoke_counts_do_not_reconcile"
    ):
        _reconcile_smoke_rows(valid[1:])


def test_source_query_and_requirements_keep_test_and_unpinned_torch_out() -> None:
    root = Path(__file__).parents[1]
    source = (root / "src" / "complaint_triage" / "transformer_training.py").read_text(
        encoding="utf-8"
    )
    requirements = (root / "requirements-transformer-training.txt").read_text(encoding="utf-8")

    assert "o.split_assignment = 'train'" in source
    assert "o.split_assignment = 'test'" not in source
    assert "torch==2.13.0+cu130" in requirements
    assert "2efab1e83604ca628c6d85b9e188c153690980498d1297081a9dad704919303c" in requirements


def test_safe_error_contains_no_source_values() -> None:
    output = safe_transformer_training_error(
        TransformerTrainingError("transformer_training_nonfinite_loss")
    )

    assert output["error"] == {"code": "transformer_training_nonfinite_loss"}
    assert output["privacy"] == {
        "narratives_logged": False,
        "complaint_ids_logged": False,
        "token_ids_logged": False,
        "row_values_in_output": False,
    }
