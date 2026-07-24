from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from complaint_triage import transformer_fit
from complaint_triage.transformer_dataset import LABELS
from complaint_triage.transformer_fit import (
    ARTIFACT_VERSION,
    REPORT_VERSION,
    RETENTION,
    TransformerFitError,
    _artifact_metadata,
    _build_linear_scheduler,
    _build_optimizer,
    _build_report,
    _evaluate_validation,
    _load_safetensors_model,
    _optimizer_steps_per_epoch,
    _prune_superseded_resume_files,
    _save_safetensors_model,
    _train_epoch,
    _validate_report,
    metrics_from_confusion,
    safe_transformer_fit_error,
    select_epoch,
    update_early_stopping,
)
from complaint_triage.transformer_training import BatchConfiguration


def _metrics(
    *, macro_f1: float = 0.5, worst_recall: float = 0.4, weighted_f1: float = 0.6
) -> dict[str, float]:
    return {
        "macro_f1": macro_f1,
        "worst_class_recall": worst_recall,
        "weighted_f1": weighted_f1,
    }


def _epoch(
    epoch: int,
    *,
    macro_f1: float = 0.5,
    worst_recall: float = 0.4,
    weighted_f1: float = 0.6,
) -> dict[str, object]:
    return {
        "epoch": epoch,
        "validation": {
            "metrics": _metrics(
                macro_f1=macro_f1,
                worst_recall=worst_recall,
                weighted_f1=weighted_f1,
            )
        },
    }


@pytest.mark.parametrize(
    ("left", "right", "winner"),
    [
        (_epoch(1, macro_f1=0.7, worst_recall=0.1), _epoch(2, macro_f1=0.6), 1),
        (_epoch(1, worst_recall=0.5, weighted_f1=0.1), _epoch(2, worst_recall=0.4), 1),
        (_epoch(1, weighted_f1=0.7), _epoch(2, weighted_f1=0.6), 1),
        (_epoch(1), _epoch(2), 1),
    ],
)
def test_epoch_selection_applies_approved_order(left, right, winner) -> None:
    assert select_epoch([right, left])["epoch"] == winner


def test_epoch_selection_requires_an_eligible_epoch() -> None:
    with pytest.raises(TransformerFitError, match="transformer_fit_no_eligible_epoch"):
        select_epoch([])


def test_early_stopping_uses_unrounded_minimum_improvement_and_patience_one() -> None:
    best, misses, improved = update_early_stopping(0.5, None, 0)
    assert (best, misses, improved) == (0.5, 0, True)

    best, misses, improved = update_early_stopping(0.5009, best, misses)
    assert (best, misses, improved) == (0.5, 1, False)

    best, misses, improved = update_early_stopping(0.501, best, 0)
    assert best == pytest.approx(0.501)
    assert (misses, improved) == (0, True)


def test_metrics_are_derived_from_aggregate_confusion_only() -> None:
    matrix = [[0 for _ in LABELS] for _ in LABELS]
    for index in range(len(LABELS)):
        matrix[index][index] = 2

    metrics = metrics_from_confusion(matrix, top_2_correct=22, record_count=22)

    assert metrics["accuracy"] == 1
    assert metrics["macro_f1"] == 1
    assert metrics["weighted_f1"] == 1
    assert metrics["worst_class_recall"] == 1
    assert metrics["top_2_accuracy"] == 1
    assert metrics["confusion_matrix"]["rows"] == matrix
    assert set(metrics["per_class"]) == set(LABELS)


def test_metric_counts_must_reconcile() -> None:
    matrix = [[0 for _ in LABELS] for _ in LABELS]

    with pytest.raises(TransformerFitError, match="transformer_fit_metric_counts_invalid"):
        metrics_from_confusion(matrix, top_2_correct=0, record_count=1)


def test_optimizer_steps_include_the_final_partial_accumulation_group() -> None:
    configuration = BatchConfiguration(16, 2, False)

    assert _optimizer_steps_per_epoch(394_564, configuration) == 12_331
    assert _optimizer_steps_per_epoch(33, configuration) == 2


def test_artifact_metadata_is_relative_hashed_and_local_only(tmp_path: Path) -> None:
    artifact = (
        tmp_path
        / "artifacts"
        / "cfpb"
        / "transformer"
        / "cfpb-run-20260722T130728Z-2b7815d4c850"
        / "best-model.safetensors"
    )
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"safe aggregate fixture")

    metadata = _artifact_metadata(artifact, tmp_path)

    assert metadata["relative_path"].startswith("artifacts/cfpb/transformer/")
    assert len(metadata["sha256"]) == 64
    assert metadata["byte_count"] == len(b"safe aggregate fixture")
    assert metadata["retention"] == RETENTION


def test_checkpoint_pruning_keeps_only_current_verified_generation(tmp_path: Path) -> None:
    directory = tmp_path / "artifacts" / "cfpb" / "transformer" / "run"
    directory.mkdir(parents=True)
    old_model = directory / "latest-model-epoch-1.safetensors"
    old_state = directory / "latest-training-state-epoch-1.pt"
    current_model = directory / "latest-model-epoch-2.safetensors"
    current_state = directory / "latest-training-state-epoch-2.pt"
    for path in (old_model, old_state, current_model, current_state):
        path.write_bytes(b"checkpoint")

    _prune_superseded_resume_files(directory, current_model, current_state)

    assert current_model.is_file()
    assert current_state.is_file()
    assert not old_model.exists()
    assert not old_state.exists()


def test_tiny_cuda_fit_evaluation_and_safetensors_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("CUDA is required for the transformer fit integration test")

    class TinyClassifier(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.embedding = torch.nn.Embedding(64, 8)
            self.classifier = torch.nn.Linear(8, len(LABELS))

        def forward(self, input_ids, attention_mask, token_type_ids=None):
            pooled = self.embedding(input_ids).mean(dim=1)
            return type("Output", (), {"logits": self.classifier(pooled)})()

    labels = torch.arange(len(LABELS), dtype=torch.int64)
    batch = {
        "input_ids": torch.arange(len(LABELS) * 8, dtype=torch.int64).reshape(len(LABELS), 8) % 64,
        "attention_mask": torch.ones((len(LABELS), 8), dtype=torch.int64),
        "token_type_ids": torch.zeros((len(LABELS), 8), dtype=torch.int64),
        "labels": labels,
    }

    def batches(manifest, settings, split, tokenizer, **kwargs):
        assert split in {"train", "validation"}
        return iter([{key: value.clone() for key, value in batch.items()}])

    monkeypatch.setattr(transformer_fit, "stream_collated_batches", batches)
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    model = TinyClassifier().to("cuda")
    optimizer = _build_optimizer(model, torch)
    scheduler = _build_linear_scheduler(optimizer, 1, torch)
    scaler = torch.amp.GradScaler("cuda")
    loss_function = torch.nn.CrossEntropyLoss(
        weight=torch.ones(len(LABELS), dtype=torch.float32, device="cuda")
    )
    configuration = BatchConfiguration(16, 2, False)

    training = _train_epoch(
        model,
        optimizer,
        scheduler,
        scaler,
        loss_function,
        {},
        object(),
        object(),
        configuration,
        1,
        torch,
        None,
    )
    validation = _evaluate_validation(
        model,
        loss_function,
        {},
        object(),
        object(),
        configuration,
        torch,
    )
    artifact = tmp_path / "tiny.safetensors"
    expected = model.classifier.weight.detach().clone()
    _save_safetensors_model(model, artifact, torch)
    with torch.no_grad():
        model.classifier.weight.zero_()
    _load_safetensors_model(model, artifact, torch)

    assert training["record_count"] == len(LABELS)
    assert training["optimizer_steps"] == 1
    assert training["loss_finite"] is True
    assert validation["record_count"] == len(LABELS)
    assert 0 <= validation["metrics"]["macro_f1"] <= 1
    assert artifact.is_file()
    assert artifact.stat().st_size > 0
    assert torch.equal(model.classifier.weight, expected)


def test_report_builder_produces_schema_valid_validation_only_evidence() -> None:
    class FakeCuda:
        @staticmethod
        def get_device_name(index):
            return "NVIDIA GeForce RTX 5060 Laptop GPU"

        @staticmethod
        def get_device_capability(index):
            return (12, 0)

    class FakeVersion:
        cuda = "13.0"

    class FakeTorch:
        __version__ = "2.13.0+cu130"
        version = FakeVersion()
        cuda = FakeCuda()

    counts = {label: 2 for label in LABELS}
    matrix = [[0 for _ in LABELS] for _ in LABELS]
    for index in range(len(LABELS)):
        matrix[index][index] = 1
    validation_metrics = metrics_from_confusion(matrix, top_2_correct=11, record_count=11)
    epoch = {
        "epoch": 1,
        "training": {
            "record_count": 22,
            "class_counts": counts,
            "optimizer_steps": 1,
            "mean_loss": 1.0,
            "elapsed_seconds": 2.0,
            "peak_cuda_bytes": 100,
            "loss_finite": True,
        },
        "validation": {
            "record_count": 11,
            "mean_loss": 0.8,
            "elapsed_seconds": 1.0,
            "peak_cuda_bytes": 90,
            "loss_finite": True,
            "metrics": validation_metrics,
        },
        "early_stopping": {
            "minimum_improvement_met": True,
            "monitored_best_macro_f1": 1.0,
            "non_improving_epochs": 0,
        },
    }
    artifact = {
        "relative_path": (
            "artifacts/cfpb/transformer/"
            "cfpb-run-20260722T130728Z-2b7815d4c850/best-model.safetensors"
        ),
        "sha256": "b" * 64,
        "byte_count": 10,
        "retention": RETENTION,
    }
    report = _build_report(
        {
            "run_id": "cfpb-run-20260722T130728Z-2b7815d4c850",
            "split_counts": {"train": 22, "validation": 11},
        },
        "a" * 64,
        "c" * 40,
        datetime(2026, 7, 24, 12, tzinfo=UTC),
        BatchConfiguration(16, 2, False),
        [
            {
                "per_device_batch_size": 16,
                "gradient_accumulation_steps": 2,
                "gradient_checkpointing": False,
                "status": "passed",
            }
        ],
        tuple(1.0 for _ in LABELS),
        1,
        [epoch],
        epoch,
        False,
        100,
        {
            "best_model": artifact,
            "latest_model": {
                **artifact,
                "relative_path": artifact["relative_path"].replace("best", "latest"),
            },
            "latest_training_state": {
                **artifact,
                "relative_path": artifact["relative_path"].replace(
                    "best-model.safetensors", "latest-training-state.pt"
                ),
            },
            "latest_resume_manifest": {
                **artifact,
                "relative_path": artifact["relative_path"].replace(
                    "best-model.safetensors", "latest-resume.json"
                ),
            },
        },
        FakeTorch(),
        {
            "transformers": "5.14.1",
            "tokenizers": "0.22.2",
            "safetensors": "0.8.0",
            "numpy": "2.4.3",
        },
    )

    _validate_report(report)
    encoded = json.dumps(report)
    assert report["report_version"] == REPORT_VERSION
    assert report["data"]["test_accessed"] is False
    assert report["claims"]["portfolio_promotion_approved"] is False
    assert "safe aggregate fixture" not in encoded


def test_schema_and_source_forbid_test_queries_and_public_promotion() -> None:
    root = Path(__file__).parents[1]
    schema = json.loads(
        (root / "contracts" / "cfpb-transformer-training.schema.json").read_text(encoding="utf-8")
    )
    source = (root / "src" / "complaint_triage" / "transformer_fit.py").read_text(encoding="utf-8")

    assert schema["properties"]["claims"]["properties"]["portfolio_promotion_approved"] == {
        "const": False
    }
    assert schema["properties"]["data"]["properties"]["test_accessed"] == {"const": False}
    assert "o.split_assignment = 'test'" not in source
    assert ".safetensors" in source
    assert ARTIFACT_VERSION in source


def test_safe_error_contains_no_source_values() -> None:
    output = safe_transformer_fit_error(
        TransformerFitError("transformer_fit_validation_count_mismatch")
    )

    assert output["error"] == {"code": "transformer_fit_validation_count_mismatch"}
    assert output["privacy"] == {
        "narratives_logged": False,
        "complaint_ids_logged": False,
        "token_ids_logged": False,
        "row_values_in_output": False,
    }
