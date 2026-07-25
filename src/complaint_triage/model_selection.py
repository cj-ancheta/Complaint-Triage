"""Governed CT-306 CPU benchmark and operational model selection."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import psycopg
from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.analytical_population import POPULATION_VERSION
from complaint_triage.db import DatabaseSettings
from complaint_triage.live_extraction import read_git_lineage
from complaint_triage.real_extraction import PROJECT_ROOT
from complaint_triage.taxonomy import CURRENT_PRODUCT_LABELS
from complaint_triage.temporal_split import SPLIT_VERSION
from complaint_triage.transformer_dataset import LABELS, MAXIMUM_LENGTH

REPORT_VERSION = "operational-model-selection-1.0.0"
BASELINE_REPORT_VERSION = "tfidf-logreg-selection-1.0.0"
TRANSFORMER_REPORT_VERSION = "transformer-minilm-selection-1.0.0"
COMPARISON_REPORT_VERSION = "validation-model-comparison-1.0.0"
CALIBRATION_REPORT_VERSION = "transformer-temperature-calibration-1.0.0"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-model-selection.schema.json"
SAMPLE_COUNT = 512
WARMUP_COUNT = 16
MEASURED_PASSES = 3
MEASURED_PREDICTION_COUNT = SAMPLE_COUNT * MEASURED_PASSES
BENCHMARK_START = "2024-10-01"
BENCHMARK_END = "2024-11-01"
PYTORCH_INTRAOP_THREADS = 4
PYTORCH_INTEROP_THREADS = 1
MACRO_F1_FLOOR = 0.020
WORST_RECALL_FLOOR = 0.050
P95_LATENCY_CEILING_MS = 750.0
MAX_LATENCY_CEILING_MS = 1_500.0
LOAD_TIME_CEILING_SECONDS = 30.0
PEAK_WORKING_SET_CEILING_BYTES = 2 * 1024**3
ARTIFACT_CEILING_BYTES = 256 * 1024**2
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

LineageReader = Callable[[Path], tuple[str, bool]]
Clock = Callable[[], datetime]
ArtifactVerifier = Callable[[Path, Mapping[str, Any], str], None]
BenchmarkRunner = Callable[..., Mapping[str, Mapping[str, Any]]]


class ModelSelectionError(Exception):
    """A controlled CT-306 failure containing no complaint row values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_model_selection_error(error: ModelSelectionError) -> dict[str, Any]:
    """Return a privacy-safe command error."""

    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "complaint_ids_logged": False,
            "fingerprints_logged": False,
            "predictions_logged": False,
            "per_row_timings_logged": False,
        },
    }


def select_operational_model(
    calibration_report_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    lineage_reader: LineageReader = read_git_lineage,
    clock: Clock = lambda: datetime.now(UTC),
    artifact_verifier: ArtifactVerifier | None = None,
    benchmark_runner: BenchmarkRunner | None = None,
) -> dict[str, Any]:
    """Benchmark both accepted candidates and apply the approved CT-306 rule."""

    root = repository_root.resolve()
    calibration, calibration_bytes = _load_report(
        calibration_report_path,
        root / "data" / "evaluations" / "cfpb" / "calibration",
        root / "contracts" / "cfpb-transformer-calibration.schema.json",
        CALIBRATION_REPORT_VERSION,
        "calibration",
    )
    run_id = calibration["run_id"]
    paths = _source_paths(root, run_id)
    baseline, baseline_bytes = _load_report(
        paths["baseline"],
        paths["baseline"].parent,
        root / "contracts" / "cfpb-tfidf-logreg-report.schema.json",
        BASELINE_REPORT_VERSION,
        "baseline",
    )
    transformer, transformer_bytes = _load_report(
        paths["transformer"],
        paths["transformer"].parent,
        root / "contracts" / "cfpb-transformer-training.schema.json",
        TRANSFORMER_REPORT_VERSION,
        "transformer",
    )
    comparison, comparison_bytes = _load_report(
        paths["comparison"],
        paths["comparison"].parent,
        root / "contracts" / "cfpb-validation-model-comparison.schema.json",
        COMPARISON_REPORT_VERSION,
        "comparison",
    )
    split_bytes = _load_split_bytes(paths["split"], root)
    hashes = {
        "baseline_report_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
        "transformer_report_sha256": hashlib.sha256(transformer_bytes).hexdigest(),
        "comparison_report_sha256": hashlib.sha256(comparison_bytes).hexdigest(),
        "calibration_report_sha256": hashlib.sha256(calibration_bytes).hexdigest(),
        "split_manifest_sha256": hashlib.sha256(split_bytes).hexdigest(),
    }
    _validate_source_identity(baseline, transformer, comparison, calibration, hashes)

    verify = artifact_verifier or _verify_artifact
    verify(root, baseline["artifact"], "artifacts/cfpb/tfidf-logreg/")
    verify(root, transformer["artifacts"]["best_model"], "artifacts/cfpb/transformer/")
    verify(root, calibration["artifact"], "artifacts/cfpb/transformer/")

    output_path = _report_path(root, run_id)
    if output_path.exists():
        existing = _load_existing_report(output_path, root)
        if any(existing["source"].get(key) != value for key, value in hashes.items()):
            raise ModelSelectionError("model_selection_report_identity_conflict")
        return existing

    commit_sha, clean = lineage_reader(root)
    if not SHA40_PATTERN.fullmatch(commit_sha) or not clean:
        raise ModelSelectionError("model_selection_requires_clean_commit")
    created_at = clock()
    if created_at.tzinfo is None or created_at.utcoffset() != UTC.utcoffset(created_at):
        raise ModelSelectionError("model_selection_clock_invalid")

    run_benchmarks = benchmark_runner or run_subprocess_benchmarks
    benchmark_results = dict(run_benchmarks(repository_root=root, run_id=run_id))
    benchmarks = _validate_benchmarks(benchmark_results, baseline, transformer, calibration)
    quality = _quality_evidence(comparison)
    calibration_evidence = _calibration_evidence(calibration)
    gate_results = {
        "evidence_and_lineage": True,
        "material_validation_quality": quality["gate_passed"],
        "probability_calibration": calibration_evidence["gate_passed"],
        "cpu_service_usability": _cpu_gate(benchmarks["transformer"]),
        "explainability_boundary": True,
        "complexity_and_cost_boundary": True,
    }
    all_gates_passed = all(gate_results.values())
    selected_model = "calibrated_minilm" if all_gates_passed else "tfidf_logistic_regression"
    report = {
        "report_version": REPORT_VERSION,
        "run_id": run_id,
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "source": {**hashes, "selection_implementation_commit_sha": commit_sha},
        "data": {
            "feature_input": "consumer_complaint_narrative_only",
            "evaluation_split": "validation",
            "benchmark_start_inclusive": BENCHMARK_START,
            "benchmark_end_exclusive": BENCHMARK_END,
            "selection_method": "lowest_normalized_narrative_fingerprint",
            "sample_count": SAMPLE_COUNT,
            "warmup_count": WARMUP_COUNT,
            "measured_passes": MEASURED_PASSES,
            "measured_predictions_per_candidate": MEASURED_PREDICTION_COUNT,
            "labels": list(LABELS),
            "test_accessed": False,
        },
        "utility_rule": {
            "adr": "docs/decisions/0015-proposed-operational-model-selection.md",
            "method": "all_gates_required_with_tfidf_fallback",
            "quality_floors": {
                "macro_f1_delta": MACRO_F1_FLOOR,
                "worst_class_recall_delta": WORST_RECALL_FLOOR,
                "accuracy_may_decrease": False,
                "weighted_f1_may_decrease": False,
                "maximum_classes_with_lower_f1": 1,
            },
            "cpu_ceilings": {
                "p95_latency_ms": P95_LATENCY_CEILING_MS,
                "maximum_latency_ms": MAX_LATENCY_CEILING_MS,
                "load_seconds": LOAD_TIME_CEILING_SECONDS,
                "peak_working_set_bytes": PEAK_WORKING_SET_CEILING_BYTES,
                "artifact_bytes": ARTIFACT_CEILING_BYTES,
            },
        },
        "quality": quality,
        "calibration": calibration_evidence,
        "benchmarks": benchmarks,
        "assessment": {
            "explainability": {
                "gate_passed": True,
                "baseline": "inspectable_sparse_coefficients_with_noncausal_wording",
                "transformer": "global_per_class_and_example_based_evidence_only",
                "local_transformer_reason_codes": "not_authorized",
                "class_specific_calibration_limitation_carried_forward": True,
            },
            "complexity_and_cost": {
                "gate_passed": True,
                "gpu_required": False,
                "external_model_request_required": False,
                "paid_inference_required": False,
                "distributed_orchestration_required": False,
                "provider_price_assessed": False,
                "transformer_has_larger_dependency_and_maintenance_surface": True,
            },
            "selective_accuracy_after_abstention": {
                "status": "deferred_to_phase_4_under_separate_approved_policy",
                "operational_threshold_selected": False,
                "reason": "ct306_selects_the_candidate_before_threshold_analysis",
            },
        },
        "decision": {
            "gate_results": gate_results,
            "all_gates_passed": all_gates_passed,
            "selected_operational_candidate": selected_model,
            "fallback_applied": not all_gates_passed,
            "failed_gates": [name for name, passed in gate_results.items() if not passed],
            "next_gate": "phase_4_abstention_and_governance_evaluation",
        },
        "claims": {
            "operational_candidate_selected": True,
            "final_test_access_authorized": False,
            "operational_threshold_selected": False,
            "deployment_authorized": False,
            "portfolio_promotion_approved": False,
            "production_performance_claimed": False,
        },
        "privacy": {
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "contains_fingerprints": False,
            "contains_predictions": False,
            "contains_per_row_timings": False,
            "git_tracking_allowed": True,
        },
    }
    _validate_report(report, root)
    _atomic_json(output_path, report)
    return report


def run_subprocess_benchmarks(*, repository_root: Path, run_id: str) -> dict[str, Any]:
    """Run each candidate in a fresh CPU-only Python subprocess."""

    results: dict[str, Any] = {}
    for candidate in ("baseline", "transformer"):
        environment = dict(os.environ)
        environment.update(
            {
                "CUDA_VISIBLE_DEVICES": "-1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "TOKENIZERS_PARALLELISM": "false",
            }
        )
        command = [
            sys.executable,
            "-m",
            "complaint_triage.model_selection",
            "--ct306-worker",
            candidate,
            "--repository-root",
            str(repository_root),
            "--run-id",
            run_id,
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=repository_root,
                env=environment,
                capture_output=True,
                text=True,
                timeout=1_800,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ModelSelectionError(
                "model_selection_worker_execution_failed", candidate=candidate
            ) from error
        if completed.returncode != 0:
            raise ModelSelectionError("model_selection_worker_failed", candidate=candidate)
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ModelSelectionError(
                "model_selection_worker_output_invalid", candidate=candidate
            ) from error
        results[candidate] = result
    return results


def iter_benchmark_rows(run_id: str, settings: DatabaseSettings) -> Iterable[tuple[str, str, str]]:
    """Read the deterministic October validation-only benchmark workload."""

    query = """
        SELECT s.narrative, p.target_product, o.narrative_fingerprint_sha256
        FROM analytical.split_outcomes o
        JOIN analytical.population_outcomes p
          ON p.raw_batch_id = o.raw_batch_id
         AND p.source_row_ordinal = o.source_row_ordinal
         AND p.staging_transformation_version = o.staging_transformation_version
         AND p.population_version = o.population_version
        JOIN staging.complaint_outcomes s
          ON s.raw_batch_id = o.raw_batch_id
         AND s.source_row_ordinal = o.source_row_ordinal
         AND s.transformation_version = o.staging_transformation_version
        WHERE o.run_id = %s AND o.split_version = %s
          AND o.population_version = %s
          AND o.disposition = 'included'
          AND o.split_assignment = 'validation'
          AND s.date_received >= DATE '2024-10-01'
          AND s.date_received < DATE '2024-11-01'
        ORDER BY o.narrative_fingerprint_sha256
        LIMIT 512
    """
    try:
        with psycopg.connect(settings.psycopg_conninfo()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (run_id, SPLIT_VERSION, POPULATION_VERSION))
                yield from cursor.fetchall()
    except psycopg.Error as error:
        raise ModelSelectionError("model_selection_database_failed") from error


def summarize_latencies(values: Sequence[float]) -> dict[str, float | int | str]:
    """Return deterministic nearest-rank latency summaries."""

    if len(values) != MEASURED_PREDICTION_COUNT or any(
        isinstance(value, bool) or not math.isfinite(value) or value <= 0 for value in values
    ):
        raise ModelSelectionError("model_selection_latency_values_invalid")
    ordered = sorted(float(value) for value in values)

    def nearest_rank(probability: float) -> float:
        return ordered[math.ceil(probability * len(ordered)) - 1]

    return {
        "unit": "milliseconds",
        "quantile_method": "nearest_rank",
        "measurement_count": len(ordered),
        "mean": round(statistics.fmean(ordered), 6),
        "p50": round(nearest_rank(0.50), 6),
        "p95": round(nearest_rank(0.95), 6),
        "maximum": round(ordered[-1], 6),
    }


def _run_worker(candidate: str, root: Path, run_id: str) -> dict[str, Any]:
    if os.name != "nt":
        raise ModelSelectionError("model_selection_memory_platform_unsupported")
    if candidate not in {"baseline", "transformer"}:
        raise ModelSelectionError("model_selection_worker_candidate_invalid")
    rows = list(
        iter_benchmark_rows(
            run_id,
            DatabaseSettings.from_environment(env_file=root / ".env"),
        )
    )
    _validate_workload(rows)
    character_lengths = [len(narrative) for narrative, _, _ in rows]
    predictor, load_seconds, artifact_bytes, software = _load_predictor(candidate, root, run_id)
    for narrative, _, _ in rows[:WARMUP_COUNT]:
        _validate_probabilities(predictor(narrative))
    latencies: list[float] = []
    for _ in range(MEASURED_PASSES):
        for narrative, _, _ in rows:
            started = time.perf_counter_ns()
            probabilities = predictor(narrative)
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            _validate_probabilities(probabilities)
            latencies.append(elapsed_ms)
    return {
        "candidate": candidate,
        "load_seconds": round(load_seconds, 6),
        "latency": summarize_latencies(latencies),
        "peak_working_set_bytes": _windows_process_memory()["peak_working_set_bytes"],
        "artifact_bytes": artifact_bytes,
        "workload": {
            "sample_count": len(rows),
            "warmup_count": WARMUP_COUNT,
            "measured_passes": MEASURED_PASSES,
            "measured_prediction_count": len(latencies),
            "character_length": _distribution(character_lengths),
        },
        "environment": {
            "cpu": _windows_cpu_name(),
            "logical_processors": os.cpu_count(),
            "total_physical_memory_bytes": _windows_total_physical_memory(),
            "operating_system": platform.system(),
            "operating_system_release": platform.release(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "gpu_used": False,
            "network_model_loading_enabled": False,
            "pytorch_intraop_threads": PYTORCH_INTRAOP_THREADS
            if candidate == "transformer"
            else None,
            "pytorch_interop_threads": PYTORCH_INTEROP_THREADS
            if candidate == "transformer"
            else None,
            "software": software,
        },
    }


def _load_predictor(
    candidate: str, root: Path, run_id: str
) -> tuple[Callable[[str], Sequence[float]], float, int, dict[str, str]]:
    paths = _source_paths(root, run_id)
    if candidate == "baseline":
        import joblib

        report = json.loads(paths["baseline"].read_text(encoding="utf-8"))
        metadata = report["artifact"]
        _verify_artifact(root, metadata, "artifacts/cfpb/tfidf-logreg/")
        started = time.perf_counter()
        try:
            pipeline = joblib.load(root / metadata["relative_path"])
        except (OSError, ValueError, TypeError) as error:
            raise ModelSelectionError("model_selection_baseline_load_failed") from error
        load_seconds = time.perf_counter() - started
        classes = tuple(str(value) for value in getattr(pipeline, "classes_", ()))
        if classes != LABELS:
            raise ModelSelectionError("model_selection_baseline_labels_invalid")

        def predict(narrative: str) -> Sequence[float]:
            return pipeline.predict_proba([narrative])[0].tolist()

        return (
            predict,
            load_seconds,
            int(metadata["byte_count"]),
            _package_versions(("numpy", "scikit-learn", "scipy", "joblib")),
        )

    try:
        import torch
        from safetensors.torch import load_file
    except ImportError as error:
        raise ModelSelectionError("model_selection_transformer_dependency_missing") from error
    from complaint_triage.transformer_token_profile import load_pinned_tokenizer
    from complaint_triage.transformer_training import load_pinned_sequence_classifier

    torch.set_num_threads(PYTORCH_INTRAOP_THREADS)
    torch.set_num_interop_threads(PYTORCH_INTEROP_THREADS)
    transformer_report = json.loads(paths["transformer"].read_text(encoding="utf-8"))
    calibration_report = json.loads(paths["calibration"].read_text(encoding="utf-8"))
    model_metadata = transformer_report["artifacts"]["best_model"]
    calibration_metadata = calibration_report["artifact"]
    _verify_artifact(root, model_metadata, "artifacts/cfpb/transformer/")
    _verify_artifact(root, calibration_metadata, "artifacts/cfpb/transformer/")
    started = time.perf_counter()
    bundle = load_pinned_tokenizer(root)
    model = load_pinned_sequence_classifier(root)
    try:
        state = load_file(str(root / model_metadata["relative_path"]), device="cpu")
        model.load_state_dict(state, strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise ModelSelectionError("model_selection_transformer_load_failed") from error
    model.to("cpu")
    model.eval()
    try:
        calibrator = json.loads((root / calibration_metadata["relative_path"]).read_text("utf-8"))
        temperature = float(calibrator["temperature"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ModelSelectionError("model_selection_calibrator_load_failed") from error
    if (
        not math.isfinite(temperature)
        or temperature <= 0
        or not math.isclose(
            temperature, float(calibration_report["method"]["temperature"]), abs_tol=0.0
        )
    ):
        raise ModelSelectionError("model_selection_calibrator_value_mismatch")
    load_seconds = time.perf_counter() - started

    def predict(narrative: str) -> Sequence[float]:
        encoded = bundle.tokenizer(
            narrative,
            add_special_tokens=True,
            padding=False,
            truncation=True,
            max_length=MAXIMUM_LENGTH,
            return_attention_mask=True,
            return_token_type_ids=True,
            return_tensors="pt",
            verbose=False,
        )
        with torch.inference_mode():
            logits = model(**encoded).logits / temperature
            return torch.softmax(logits, dim=1)[0].tolist()

    artifact_bytes = int(model_metadata["byte_count"]) + int(calibration_metadata["byte_count"])
    return (
        predict,
        load_seconds,
        artifact_bytes,
        _package_versions(("numpy", "torch", "transformers", "tokenizers", "safetensors")),
    )


def _validate_workload(rows: Sequence[tuple[str, str, str]]) -> None:
    if len(rows) != SAMPLE_COUNT:
        raise ModelSelectionError("model_selection_sample_count_mismatch")
    previous = ""
    labels = set(CURRENT_PRODUCT_LABELS)
    for narrative, label, fingerprint in rows:
        if (
            not isinstance(narrative, str)
            or not narrative.strip()
            or label not in labels
            or not isinstance(fingerprint, str)
            or not SHA256_PATTERN.fullmatch(fingerprint)
            or fingerprint <= previous
        ):
            raise ModelSelectionError("model_selection_source_row_invalid")
        previous = fingerprint


def _validate_probabilities(values: Sequence[float]) -> None:
    if len(values) != len(LABELS):
        raise ModelSelectionError("model_selection_prediction_contract_invalid")
    probabilities = [float(value) for value in values]
    if any(
        not math.isfinite(value) or value < 0 or value > 1 for value in probabilities
    ) or not math.isclose(sum(probabilities), 1.0, abs_tol=1e-6):
        raise ModelSelectionError("model_selection_prediction_contract_invalid")


def _quality_evidence(comparison: Mapping[str, Any]) -> dict[str, Any]:
    metrics = comparison["comparison"]["shared_validation_metrics"]
    wins = comparison["comparison"]["class_f1_wins"]
    checks = {
        "macro_f1_delta_at_least_0p020": (
            metrics["macro_f1"]["delta_transformer_minus_baseline"] >= MACRO_F1_FLOOR
        ),
        "worst_class_recall_delta_at_least_0p050": (
            metrics["worst_class_recall"]["delta_transformer_minus_baseline"] >= WORST_RECALL_FLOOR
        ),
        "accuracy_not_lower": metrics["accuracy"]["delta_transformer_minus_baseline"] >= 0,
        "weighted_f1_not_lower": (metrics["weighted_f1"]["delta_transformer_minus_baseline"] >= 0),
        "at_most_one_class_f1_loss": wins["baseline"] <= 1,
    }
    return {
        "metrics": {
            name: {
                "baseline": value["baseline"],
                "transformer": value["transformer"],
                "delta_transformer_minus_baseline": value["delta_transformer_minus_baseline"],
            }
            for name, value in metrics.items()
        },
        "class_f1_wins": dict(wins),
        "checks": checks,
        "gate_passed": all(checks.values()),
    }


def _calibration_evidence(calibration: Mapping[str, Any]) -> dict[str, Any]:
    eligibility = calibration["eligibility"]
    checks = dict(eligibility["checks"])
    return {
        "method": calibration["method"]["kind"],
        "temperature": calibration["method"]["temperature"],
        "eligibility_checks": checks,
        "class_specific_calibration_limitation": True,
        "gate_passed": bool(eligibility["calibrator_eligible_for_ct306"]) and all(checks.values()),
    }


def _cpu_gate(transformer: Mapping[str, Any]) -> bool:
    return bool(
        transformer["latency"]["p95"] <= P95_LATENCY_CEILING_MS
        and transformer["latency"]["maximum"] <= MAX_LATENCY_CEILING_MS
        and transformer["load_seconds"] <= LOAD_TIME_CEILING_SECONDS
        and transformer["peak_working_set_bytes"] <= PEAK_WORKING_SET_CEILING_BYTES
        and transformer["artifact_bytes"] <= ARTIFACT_CEILING_BYTES
    )


def _validate_benchmarks(
    raw: Mapping[str, Mapping[str, Any]],
    baseline: Mapping[str, Any],
    transformer: Mapping[str, Any],
    calibration: Mapping[str, Any],
) -> dict[str, Any]:
    if set(raw) != {"baseline", "transformer"}:
        raise ModelSelectionError("model_selection_benchmark_candidates_invalid")
    expected_artifacts = {
        "baseline": int(baseline["artifact"]["byte_count"]),
        "transformer": int(transformer["artifacts"]["best_model"]["byte_count"])
        + int(calibration["artifact"]["byte_count"]),
    }
    validated: dict[str, Any] = {}
    for candidate in ("baseline", "transformer"):
        value = raw[candidate]
        try:
            latency = value["latency"]
            workload = value["workload"]
            environment = value["environment"]
            numeric = (
                value["load_seconds"],
                value["peak_working_set_bytes"],
                value["artifact_bytes"],
                latency["mean"],
                latency["p50"],
                latency["p95"],
                latency["maximum"],
            )
        except (KeyError, TypeError) as error:
            raise ModelSelectionError(
                "model_selection_benchmark_result_invalid", candidate=candidate
            ) from error
        if (
            value.get("candidate") != candidate
            or any(
                isinstance(item, bool) or not math.isfinite(float(item)) or item <= 0
                for item in numeric
            )
            or value["artifact_bytes"] != expected_artifacts[candidate]
            or latency.get("unit") != "milliseconds"
            or latency.get("quantile_method") != "nearest_rank"
            or latency.get("measurement_count") != MEASURED_PREDICTION_COUNT
            or not (latency["p50"] <= latency["p95"] <= latency["maximum"])
            or workload.get("sample_count") != SAMPLE_COUNT
            or workload.get("warmup_count") != WARMUP_COUNT
            or workload.get("measured_passes") != MEASURED_PASSES
            or workload.get("measured_prediction_count") != MEASURED_PREDICTION_COUNT
            or environment.get("gpu_used") is not False
            or environment.get("network_model_loading_enabled") is not False
        ):
            raise ModelSelectionError(
                "model_selection_benchmark_result_invalid", candidate=candidate
            )
        validated[candidate] = dict(value)
    if (
        validated["baseline"]["workload"]["character_length"]
        != validated["transformer"]["workload"]["character_length"]
        or validated["baseline"]["environment"]["cpu"]
        != validated["transformer"]["environment"]["cpu"]
        or validated["baseline"]["environment"]["total_physical_memory_bytes"]
        != validated["transformer"]["environment"]["total_physical_memory_bytes"]
    ):
        raise ModelSelectionError("model_selection_benchmark_environment_mismatch")
    validated["relative_ratios"] = {
        "transformer_to_baseline_load_time": round(
            validated["transformer"]["load_seconds"] / validated["baseline"]["load_seconds"],
            6,
        ),
        "transformer_to_baseline_p50_latency": round(
            validated["transformer"]["latency"]["p50"] / validated["baseline"]["latency"]["p50"],
            6,
        ),
        "transformer_to_baseline_p95_latency": round(
            validated["transformer"]["latency"]["p95"] / validated["baseline"]["latency"]["p95"],
            6,
        ),
        "transformer_to_baseline_peak_working_set": round(
            validated["transformer"]["peak_working_set_bytes"]
            / validated["baseline"]["peak_working_set_bytes"],
            6,
        ),
        "transformer_to_baseline_artifact_bytes": round(
            validated["transformer"]["artifact_bytes"] / validated["baseline"]["artifact_bytes"],
            6,
        ),
    }
    return validated


def _validate_source_identity(
    baseline: Mapping[str, Any],
    transformer: Mapping[str, Any],
    comparison: Mapping[str, Any],
    calibration: Mapping[str, Any],
    hashes: Mapping[str, str],
) -> None:
    run_id = calibration["run_id"]
    if any(report["run_id"] != run_id for report in (baseline, transformer, comparison)):
        raise ModelSelectionError("model_selection_run_identity_mismatch")
    split_hash = hashes["split_manifest_sha256"]
    if (
        baseline["source"]["split_manifest_sha256"] != split_hash
        or transformer["source"]["split_manifest_sha256"] != split_hash
        or comparison["source"]["split_manifest_sha256"] != split_hash
        or calibration["source"]["split_manifest_sha256"] != split_hash
        or comparison["source"]["baseline_report_sha256"] != hashes["baseline_report_sha256"]
        or comparison["source"]["transformer_report_sha256"] != hashes["transformer_report_sha256"]
        or calibration["source"]["transformer_report_sha256"] != hashes["transformer_report_sha256"]
        or calibration["source"]["comparison_report_sha256"] != hashes["comparison_report_sha256"]
    ):
        raise ModelSelectionError("model_selection_source_identity_mismatch")
    if (
        baseline["data"]["test_accessed"]
        or transformer["data"]["test_accessed"]
        or comparison["data"]["test_accessed"]
        or calibration["data"]["test_accessed"]
        or comparison["claims"]["operational_model_selected"]
        or calibration["eligibility"]["final_operational_model_selected"]
        or comparison["utility_proposal"]["candidate_for_calibration"] != "transformer_minilm"
    ):
        raise ModelSelectionError("model_selection_source_boundary_invalid")
    labels = list(LABELS)
    if any(
        report["data"]["labels"] != labels
        for report in (baseline, transformer, comparison, calibration)
    ):
        raise ModelSelectionError("model_selection_taxonomy_mismatch")


def _source_paths(root: Path, run_id: str) -> dict[str, Path]:
    return {
        "baseline": root
        / "data/evaluations/cfpb/tfidf-logreg"
        / f"{run_id}-{BASELINE_REPORT_VERSION}.json",
        "transformer": root
        / "data/evaluations/cfpb/transformer"
        / f"{run_id}-{TRANSFORMER_REPORT_VERSION}.json",
        "comparison": root
        / "data/evaluations/cfpb/model-comparison"
        / f"{run_id}-{COMPARISON_REPORT_VERSION}.json",
        "calibration": root
        / "data/evaluations/cfpb/calibration"
        / f"{run_id}-{CALIBRATION_REPORT_VERSION}.json",
        "split": root / "data/manifests/cfpb/splits" / f"{run_id}-split-1.0.0.json",
    }


def _load_report(
    path: Path, expected_parent: Path, schema_path: Path, expected_version: str, name: str
) -> tuple[dict[str, Any], bytes]:
    if path.resolve().parent != expected_parent.resolve():
        raise ModelSelectionError(f"unsafe_model_selection_{name}_report_path")
    try:
        encoded = path.read_bytes()
        report = json.loads(encoded)
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelSelectionError(f"model_selection_{name}_report_unreadable") from error
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if not isinstance(report, dict) or errors or report.get("report_version") != expected_version:
        raise ModelSelectionError(
            f"model_selection_{name}_report_schema_invalid", issue_count=len(errors)
        )
    return report, encoded


def _load_split_bytes(path: Path, root: Path) -> bytes:
    if path.resolve().parent != (root / "data/manifests/cfpb/splits").resolve():
        raise ModelSelectionError("unsafe_model_selection_split_manifest_path")
    try:
        return path.read_bytes()
    except OSError as error:
        raise ModelSelectionError("model_selection_split_manifest_unreadable") from error


def _verify_artifact(root: Path, metadata: Mapping[str, Any], required_prefix: str) -> None:
    relative = metadata.get("relative_path")
    digest = metadata.get("sha256")
    byte_count = metadata.get("byte_count")
    if (
        not isinstance(relative, str)
        or not relative.startswith(required_prefix)
        or not isinstance(digest, str)
        or not SHA256_PATTERN.fullmatch(digest)
        or isinstance(byte_count, bool)
        or not isinstance(byte_count, int)
        or byte_count < 1
    ):
        raise ModelSelectionError("model_selection_artifact_metadata_invalid")
    path = (root / relative).resolve()
    try:
        path.relative_to((root / required_prefix).resolve())
        if path.stat().st_size != byte_count or _file_sha256(path) != digest:
            raise ModelSelectionError("model_selection_artifact_hash_mismatch")
    except (OSError, ValueError) as error:
        raise ModelSelectionError("model_selection_artifact_unreadable") from error


def _distribution(values: Sequence[int]) -> dict[str, float | int | str]:
    if not values or any(isinstance(value, bool) or value <= 0 for value in values):
        raise ModelSelectionError("model_selection_character_length_invalid")
    ordered = sorted(values)
    return {
        "unit": "unicode_code_points",
        "minimum": ordered[0],
        "mean": round(statistics.fmean(ordered), 6),
        "p50": ordered[math.ceil(0.50 * len(ordered)) - 1],
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
        "maximum": ordered[-1],
    }


def _windows_process_memory() -> dict[str, int]:
    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    if not psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    ):
        raise ModelSelectionError("model_selection_memory_measurement_failed")
    return {
        "working_set_bytes": int(counters.WorkingSetSize),
        "peak_working_set_bytes": int(counters.PeakWorkingSetSize),
    }


def _windows_total_physical_memory() -> int:
    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatusEx)]
    kernel32.GlobalMemoryStatusEx.restype = ctypes.c_int
    if not kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ModelSelectionError("model_selection_memory_measurement_failed")
    return int(status.ullTotalPhys)


def _windows_cpu_name() -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
    except (ImportError, OSError) as error:
        raise ModelSelectionError("model_selection_cpu_identity_failed") from error
    result = " ".join(str(value).split())
    if not result:
        raise ModelSelectionError("model_selection_cpu_identity_failed")
    return result


def _package_versions(names: Sequence[str]) -> dict[str, str]:
    result = {"python": platform.python_version()}
    try:
        result.update({name: version(name) for name in names})
    except PackageNotFoundError as error:
        raise ModelSelectionError("model_selection_software_metadata_failed") from error
    return result


def _load_existing_report(path: Path, root: Path) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ModelSelectionError("model_selection_report_unreadable") from error
    _validate_report(report, root)
    return report


def _validate_report(report: Mapping[str, Any], root: Path) -> None:
    try:
        schema = json.loads(
            (root / "contracts/cfpb-model-selection.schema.json").read_text("utf-8")
        )
    except (OSError, json.JSONDecodeError) as error:
        raise ModelSelectionError("model_selection_schema_unreadable") from error
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise ModelSelectionError("model_selection_report_schema_invalid", issue_count=len(errors))


def _report_path(root: Path, run_id: str) -> Path:
    return root / "data/evaluations/cfpb/model-selection" / f"{run_id}-{REPORT_VERSION}.json"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as destination:
            destination.write(encoded)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise ModelSelectionError("model_selection_report_write_failed") from error
    finally:
        temporary.unlink(missing_ok=True)


def _worker_main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--ct306-worker", choices=("baseline", "transformer"), required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = _run_worker(args.ct306_worker, args.repository_root.resolve(), args.run_id)
    except ModelSelectionError as error:
        print(json.dumps(safe_model_selection_error(error), sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_worker_main(sys.argv[1:]))
