"""Aggregate-only reconciliation report for one completed real extraction run."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import psycopg
from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.analytical_population import POPULATION_VERSION
from complaint_triage.db import DatabaseSettings
from complaint_triage.real_extraction import PROJECT_ROOT, RUN_SCHEMA_PATH
from complaint_triage.staging import TRANSFORMATION_VERSION


class RealRunReportError(Exception):
    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def report_real_run(
    run_manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
) -> dict[str, Any]:
    """Reconcile all layers and atomically publish a metadata-only run report."""

    root = repository_root.resolve()
    manifest_path = run_manifest_path.resolve()
    expected_parent = (root / "data" / "manifests" / "cfpb" / "runs").resolve()
    if manifest_path.parent != expected_parent:
        raise RealRunReportError("unsafe_run_manifest_path")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = json.loads(RUN_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RealRunReportError("run_manifest_unreadable") from error
    if list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)):
        raise RealRunReportError("run_manifest_schema_invalid")

    batch_ids = [shard["batch_id"] for shard in manifest["shards"]]
    manifest_count = sum(shard["returned_record_count"] for shard in manifest["shards"])
    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")
    try:
        with psycopg.connect(database_settings.psycopg_conninfo()) as connection:
            with connection.cursor() as cursor:
                raw = _one(
                    cursor,
                    """
                    SELECT count(*), coalesce(sum(returned_record_count), 0),
                           coalesce(sum(inserted_record_count), 0)
                    FROM raw.ingestion_batches
                    WHERE batch_id = ANY(%s)
                    """,
                    (batch_ids,),
                )
                staging = _one(
                    cursor,
                    """
                    SELECT count(*), coalesce(sum(input_record_count), 0),
                           coalesce(sum(accepted_record_count), 0),
                           coalesce(sum(quarantined_record_count), 0),
                           coalesce(sum(output_record_count), 0)
                    FROM staging.transformation_batches
                    WHERE raw_batch_id = ANY(%s) AND transformation_version = %s
                    """,
                    (batch_ids, TRANSFORMATION_VERSION),
                )
                population = _one(
                    cursor,
                    """
                    SELECT count(*), coalesce(sum(input_record_count), 0),
                           coalesce(sum(eligible_record_count), 0),
                           coalesce(sum(excluded_record_count), 0),
                           coalesce(sum(output_record_count), 0), max(reported_at)
                    FROM analytical.population_runs
                    WHERE raw_batch_id = ANY(%s)
                      AND staging_transformation_version = %s
                      AND population_version = %s
                    """,
                    (batch_ids, TRANSFORMATION_VERSION, POPULATION_VERSION),
                )
                exclusion_counts = _grouped(
                    cursor,
                    """
                    SELECT reason, count(*)
                    FROM analytical.population_outcomes,
                         unnest(exclusion_reasons) AS reason
                    WHERE raw_batch_id = ANY(%s)
                      AND staging_transformation_version = %s
                      AND population_version = %s
                    GROUP BY reason ORDER BY reason
                    """,
                    (batch_ids, TRANSFORMATION_VERSION, POPULATION_VERSION),
                )
                product_counts = _grouped(
                    cursor,
                    """
                    SELECT target_product, count(*)
                    FROM analytical.population_outcomes
                    WHERE raw_batch_id = ANY(%s)
                      AND staging_transformation_version = %s
                      AND population_version = %s
                      AND eligibility_status = 'eligible'
                    GROUP BY target_product ORDER BY target_product
                    """,
                    (batch_ids, TRANSFORMATION_VERSION, POPULATION_VERSION),
                )
                language_counts = _grouped(
                    cursor,
                    """
                    SELECT detected_language, count(*)
                    FROM analytical.population_outcomes
                    WHERE raw_batch_id = ANY(%s)
                      AND staging_transformation_version = %s
                      AND population_version = %s
                      AND detected_language IS NOT NULL
                    GROUP BY detected_language ORDER BY detected_language
                    """,
                    (batch_ids, TRANSFORMATION_VERSION, POPULATION_VERSION),
                )
                lengths = _one(
                    cursor,
                    """
                    SELECT min(narrative_char_count), max(narrative_char_count),
                           avg(narrative_char_count)
                    FROM analytical.population_outcomes
                    WHERE raw_batch_id = ANY(%s)
                      AND staging_transformation_version = %s
                      AND population_version = %s
                      AND eligibility_status = 'eligible'
                    """,
                    (batch_ids, TRANSFORMATION_VERSION, POPULATION_VERSION),
                )
    except psycopg.Error as error:
        raise RealRunReportError("database_report_failed") from error

    report = _assemble_report(
        manifest=manifest,
        manifest_count=manifest_count,
        raw=raw,
        staging=staging,
        population=population,
        exclusion_counts=exclusion_counts,
        product_counts=product_counts,
        language_counts=language_counts,
        lengths=lengths,
    )
    report_path = root / "data" / "manifests" / "cfpb" / "reports" / f"{manifest['run_id']}.json"
    _atomic_json(report_path, report)
    return report


def _assemble_report(
    *,
    manifest: Mapping[str, Any],
    manifest_count: int,
    raw: Sequence[Any],
    staging: Sequence[Any],
    population: Sequence[Any],
    exclusion_counts: Mapping[str, int],
    product_counts: Mapping[str, int],
    language_counts: Mapping[str, int],
    lengths: Sequence[Any],
) -> dict[str, Any]:
    expected_shards = int(manifest["partition"]["shard_count"])
    checks = {
        "all_raw_batches_present": raw[0] == expected_shards,
        "raw_counts_reconcile": raw[1] == raw[2] == manifest_count,
        "all_staging_batches_present": staging[0] == expected_shards,
        "staging_counts_reconcile": staging[1] == staging[4] == manifest_count,
        "staging_statuses_reconcile": staging[2] + staging[3] == staging[4],
        "all_population_batches_present": population[0] == expected_shards,
        "population_counts_reconcile": population[1] == population[4] == manifest_count,
        "population_statuses_reconcile": population[2] + population[3] == population[4],
        "eligible_products_reconcile": sum(product_counts.values()) == population[2],
        "exclusion_reasons_cover_excluded": sum(exclusion_counts.values()) >= population[3],
    }
    if not all(checks.values()):
        failed = sorted(key for key, passed in checks.items() if not passed)
        raise RealRunReportError("run_reconciliation_failed", failed_check_count=len(failed))
    reported_at = population[5]
    return {
        "status": "reported",
        "report_version": "cfpb-real-run-population-v1",
        "run_id": manifest["run_id"],
        "reported_at_utc": reported_at.isoformat().replace("+00:00", "Z"),
        "lineage": manifest["lineage"],
        "retention": manifest["policy"],
        "versions": {
            "staging_transformation": TRANSFORMATION_VERSION,
            "analytical_population": POPULATION_VERSION,
        },
        "counts": {
            "shard_count": expected_shards,
            "input_record_count": int(population[1]),
            "staging_accepted_record_count": int(staging[2]),
            "staging_quarantined_record_count": int(staging[3]),
            "eligible_record_count": int(population[2]),
            "excluded_record_count": int(population[3]),
            "eligible_rate": round(int(population[2]) / int(population[1]), 6),
        },
        "exclusion_reason_counts": dict(exclusion_counts),
        "eligible_counts_by_product": dict(product_counts),
        "detected_language_counts": dict(language_counts),
        "eligible_narrative_length": {
            "minimum": lengths[0],
            "maximum": lengths[1],
            "mean": round(float(lengths[2]), 3),
        },
        "checks": checks,
        "privacy": {
            "contains_row_values": False,
            "narratives_in_report": False,
            "source_values_logged": False,
        },
    }


def safe_real_run_report_error(error: RealRunReportError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {"contains_row_values": False, "narratives_in_report": False},
    }


def _one(cursor: psycopg.Cursor[Any], query: str, parameters: tuple[Any, ...]) -> tuple[Any, ...]:
    cursor.execute(query, parameters)
    row = cursor.fetchone()
    if row is None:
        raise RealRunReportError("database_report_missing")
    return tuple(row)


def _grouped(
    cursor: psycopg.Cursor[Any], query: str, parameters: tuple[Any, ...]
) -> dict[str, int]:
    cursor.execute(query, parameters)
    return {str(row[0]): int(row[1]) for row in cursor.fetchall()}


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != encoded:
            raise RealRunReportError("report_identity_conflict")
        return
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as destination:
            destination.write(encoded)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
