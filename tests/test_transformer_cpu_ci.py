import os
from importlib.metadata import version

import pytest


@pytest.mark.cpu_transformer
def test_locked_cpu_transformer_stack_computes_and_round_trips_safetensors(tmp_path) -> None:
    if os.environ.get("CT_REQUIRE_CPU_TRANSFORMER") != "1":
        pytest.skip("Set CT_REQUIRE_CPU_TRANSFORMER=1 in the Linux CPU transformer job")

    import torch
    from safetensors.torch import load_file, save_file
    from transformers import default_data_collator

    assert version("torch") == "2.13.0+cpu"
    assert version("transformers") == "5.14.1"
    assert version("tokenizers") == "0.22.2"
    assert version("safetensors") == "0.8.0"
    assert torch.cuda.is_available() is False

    batch = default_data_collator(
        [
            {"input_ids": [1, 2, 3], "attention_mask": [1, 1, 1], "labels": 0},
            {"input_ids": [4, 5, 6], "attention_mask": [1, 1, 1], "labels": 1},
        ]
    )
    assert batch["input_ids"].device.type == "cpu"
    assert tuple(batch["input_ids"].shape) == (2, 3)

    weights = torch.tensor([[1.0, -1.0, 0.5], [0.25, 0.5, -0.75]])
    logits = batch["input_ids"].to(torch.float32) @ weights.T
    assert torch.equal(logits, torch.tensor([[0.5, -1.0], [2.0, -1.0]]))

    artifact = tmp_path / "cpu-ci.safetensors"
    save_file({"weights": weights.contiguous()}, artifact)
    restored = load_file(artifact, device="cpu")
    assert torch.equal(restored["weights"], weights)
