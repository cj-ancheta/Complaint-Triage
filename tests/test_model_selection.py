import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from complaint_triage.model_selection import (
    MEASURED_PREDICTION_COUNT,
    REPORT_SCHEMA_PATH,
    ModelSelectionError,
    _windows_process_memory,
    _windows_total_physical_memory,
    run_subprocess_benchmarks,
    safe_model_selection_error,
    select_operational_model,
    summarize_latencies,
)


def _copy_sources(root: Path) -> Path:
    source_root = Path(__file__).parents[1]
    directories = (
        "data/evaluations/cfpb/tfidf-logreg",
        "data/evaluations/cfpb/transformer",
        "data/evaluations/cfpb/model-comparison",
        "data/evaluations/cfpb/calibration",
        "data/manifests/cfpb/splits",
    )
    for relative in directories:
        source = next((source_root / relative).glob("*.json"))
        destination = root / relative / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    for source in (source_root / "contracts").glob("*.schema.json"):
        destination = root / "contracts" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    return next((root / "data/evaluations/cfpb/calibration").glob("*.json"))


def _candidate(
    name: str,
    *,
    artifact_bytes: int,
    load_seconds: float,
    p50: float,
    p95: float,
    maximum: float,
    peak_bytes: int,
) -> dict:
    return {
        "candidate": name,
        "load_seconds": load_seconds,
        "latency": {
            "unit": "milliseconds",
            "quantile_method": "nearest_rank",
            "measurement_count": 1536,
            "mean": (p50 + p95) / 2,
            "p50": p50,
            "p95": p95,
            "maximum": maximum,
        },
        "peak_working_set_bytes": peak_bytes,
        "artifact_bytes": artifact_bytes,
        "workload": {
            "sample_count": 512,
            "warmup_count": 16,
            "measured_passes": 3,
            "measured_prediction_count": 1536,
            "character_length": {
                "unit": "unicode_code_points",
                "minimum": 20,
                "mean": 840.5,
                "p50": 600,
                "p95": 2400,
                "maximum": 5000,
            },
        },
        "environment": {
            "cpu": "Intel(R) Core(TM) Ultra 7 255HX",
            "logical_processors": 20,
            "total_physical_memory_bytes": 33_752_997_888,
            "operating_system": "Windows",
            "operating_system_release": "11",
            "architecture": "AMD64",
            "python": "3.12.10",
            "gpu_used": False,
            "network_model_loading_enabled": False,
            "pytorch_intraop_threads": 4 if name == "transformer" else None,
            "pytorch_interop_threads": 1 if name == "transformer" else None,
            "software": {"python": "3.12.10", "numpy": "2.5.1"},
        },
    }


def _benchmarks(root: Path, *, transformer_p95: float = 120.0) -> dict:
    baseline = json.loads(
        next((root / "data/evaluations/cfpb/tfidf-logreg").glob("*.json")).read_text(
            encoding="utf-8"
        )
    )
    transformer = json.loads(
        next((root / "data/evaluations/cfpb/transformer").glob("*.json")).read_text(
            encoding="utf-8"
        )
    )
    calibration = json.loads(
        next((root / "data/evaluations/cfpb/calibration").glob("*.json")).read_text(
            encoding="utf-8"
        )
    )
    return {
        "baseline": _candidate(
            "baseline",
            artifact_bytes=baseline["artifact"]["byte_count"],
            load_seconds=0.8,
            p50=3.0,
            p95=5.0,
            maximum=8.0,
            peak_bytes=300_000_000,
        ),
        "transformer": _candidate(
            "transformer",
            artifact_bytes=(
                transformer["artifacts"]["best_model"]["byte_count"]
                + calibration["artifact"]["byte_count"]
            ),
            load_seconds=6.0,
            p50=80.0,
            p95=transformer_p95,
            maximum=max(200.0, transformer_p95),
            peak_bytes=900_000_000,
        ),
    }


def _select(root: Path, calibration: Path, *, transformer_p95: float = 120.0):
    return select_operational_model(
        calibration,
        repository_root=root,
        lineage_reader=lambda _: ("a" * 40, True),
        clock=lambda: datetime(2026, 7, 25, 14, tzinfo=UTC),
        artifact_verifier=lambda root, metadata, prefix: None,
        benchmark_runner=lambda **kwargs: _benchmarks(root, transformer_p95=transformer_p95),
    )


def test_all_gates_select_calibrated_minilm_and_replay(tmp_path: Path) -> None:
    calibration = _copy_sources(tmp_path)

    report = _select(tmp_path, calibration)

    assert report["decision"]["all_gates_passed"] is True
    assert report["decision"]["selected_operational_candidate"] == "calibrated_minilm"
    assert report["decision"]["failed_gates"] == []
    assert report["quality"]["gate_passed"] is True
    assert report["calibration"]["gate_passed"] is True
    assert report["claims"]["portfolio_promotion_approved"] is False
    assert report["data"]["test_accessed"] is False

    replay = select_operational_model(
        calibration,
        repository_root=tmp_path,
        lineage_reader=lambda _: ("b" * 40, False),
        artifact_verifier=lambda root, metadata, prefix: None,
        benchmark_runner=lambda **kwargs: pytest.fail("replay must not rerun benchmarks"),
    )
    assert replay == report


def test_cpu_gate_failure_selects_tfidf_fallback(tmp_path: Path) -> None:
    calibration = _copy_sources(tmp_path)

    report = _select(tmp_path, calibration, transformer_p95=751.0)

    assert report["decision"]["all_gates_passed"] is False
    assert report["decision"]["selected_operational_candidate"] == "tfidf_logistic_regression"
    assert report["decision"]["fallback_applied"] is True
    assert report["decision"]["failed_gates"] == ["cpu_service_usability"]


def test_mismatched_workloads_fail_closed(tmp_path: Path) -> None:
    calibration = _copy_sources(tmp_path)
    results = _benchmarks(tmp_path)
    results["transformer"]["workload"]["character_length"]["maximum"] += 1

    with pytest.raises(ModelSelectionError, match="model_selection_benchmark_environment_mismatch"):
        select_operational_model(
            calibration,
            repository_root=tmp_path,
            lineage_reader=lambda _: ("a" * 40, True),
            artifact_verifier=lambda root, metadata, prefix: None,
            benchmark_runner=lambda **kwargs: results,
        )


def test_dirty_implementation_is_rejected_before_benchmark(tmp_path: Path) -> None:
    calibration = _copy_sources(tmp_path)

    with pytest.raises(ModelSelectionError, match="model_selection_requires_clean_commit"):
        select_operational_model(
            calibration,
            repository_root=tmp_path,
            lineage_reader=lambda _: ("a" * 40, False),
            artifact_verifier=lambda root, metadata, prefix: None,
            benchmark_runner=lambda **kwargs: pytest.fail("dirty run must not benchmark"),
        )


def test_latency_summary_uses_nearest_rank() -> None:
    values = [float(value) for value in range(1, MEASURED_PREDICTION_COUNT + 1)]

    result = summarize_latencies(values)

    assert result["measurement_count"] == 1536
    assert result["p50"] == 768.0
    assert result["p95"] == 1460.0
    assert result["maximum"] == 1536.0


def test_subprocess_benchmarks_are_offline_cpu_only(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        candidate = command[command.index("--ct306-worker") + 1]
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"candidate": candidate}))

    monkeypatch.setattr("complaint_triage.model_selection.subprocess.run", run)

    result = run_subprocess_benchmarks(repository_root=tmp_path, run_id="run-123")

    assert result == {
        "baseline": {"candidate": "baseline"},
        "transformer": {"candidate": "transformer"},
    }
    assert len(calls) == 2
    for command, kwargs in calls:
        assert command[0] == os.sys.executable
        assert kwargs["cwd"] == tmp_path
        assert kwargs["timeout"] == 1_800
        assert kwargs["check"] is False
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "-1"
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        assert kwargs["env"]["TRANSFORMERS_OFFLINE"] == "1"


@pytest.mark.parametrize(
    ("outcome", "expected_code"),
    [
        (
            subprocess.TimeoutExpired(cmd="worker", timeout=1_800),
            "model_selection_worker_execution_failed",
        ),
        (subprocess.CompletedProcess([], 7, stdout=""), "model_selection_worker_failed"),
        (
            subprocess.CompletedProcess([], 0, stdout="not-json"),
            "model_selection_worker_output_invalid",
        ),
    ],
)
def test_subprocess_benchmark_failures_are_safe(
    monkeypatch, tmp_path: Path, outcome, expected_code: str
) -> None:
    def run(*args, **kwargs):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr("complaint_triage.model_selection.subprocess.run", run)

    with pytest.raises(ModelSelectionError, match=expected_code) as error:
        run_subprocess_benchmarks(repository_root=tmp_path, run_id="run-123")

    assert error.value.details == {"candidate": "baseline"}


@pytest.mark.skipif(os.name != "nt", reason="CT-306 reference implementation is Windows-only")
def test_windows_memory_measurement_returns_positive_byte_counts() -> None:
    process = _windows_process_memory()

    assert process["working_set_bytes"] > 0
    assert process["peak_working_set_bytes"] >= process["working_set_bytes"]
    assert _windows_total_physical_memory() > process["working_set_bytes"]


def test_safe_error_schema_and_query_exclude_row_values_and_test() -> None:
    result = safe_model_selection_error(
        ModelSelectionError("model_selection_worker_failed", candidate="transformer")
    )
    schema = json.loads(REPORT_SCHEMA_PATH.read_text(encoding="utf-8"))
    source = (Path(__file__).parents[1] / "src/complaint_triage/model_selection.py").read_text(
        encoding="utf-8"
    )

    assert result["error"] == {
        "code": "model_selection_worker_failed",
        "candidate": "transformer",
    }
    assert result["privacy"]["narratives_logged"] is False
    assert schema["properties"]["data"]["properties"]["test_accessed"] == {"const": False}
    assert "o.split_assignment = 'validation'" in source
    assert "o.split_assignment = 'test'" not in source
    assert "SELECT s.narrative, p.target_product, o.narrative_fingerprint_sha256" in source
    assert "contains_per_row_timings" in source
