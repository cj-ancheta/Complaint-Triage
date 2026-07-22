"""Versioned temporal splitting with normalized duplicate isolation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from jsonschema import Draft202012Validator, FormatChecker

from complaint_triage.analytical_population import POPULATION_VERSION, TAXONOMY_VERSION
from complaint_triage.db import DatabaseSettings
from complaint_triage.live_extraction import read_git_lineage
from complaint_triage.real_extraction import PROJECT_ROOT, RUN_SCHEMA_PATH
from complaint_triage.staging import TRANSFORMATION_VERSION

SPLIT_VERSION = "1.0.0"
FINGERPRINT_VERSION = "nfc-casefold-whitespace-sha256-v1"
WINDOW_START = date(2023, 9, 1)
TRAIN_END_EXCLUSIVE = date(2024, 9, 1)
VALIDATION_END_EXCLUSIVE = date(2024, 11, 1)
WINDOW_END_EXCLUSIVE = date(2025, 1, 1)
SPLIT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "cfpb-temporal-split-manifest.schema.json"
SHA40_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FETCH_SIZE = 2_000

LineageReader = Callable[[Path], tuple[str, bool]]


class TemporalSplitError(Exception):
    """A controlled split failure that contains no source row values."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


def safe_temporal_split_error(error: TemporalSplitError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "complaint_ids_logged": False,
            "row_values_in_report": False,
        },
    }


def narrative_fingerprint(narrative: str) -> str:
    """Return the approved conservative duplicate fingerprint."""

    if not isinstance(narrative, str):
        raise TemporalSplitError("split_narrative_contract_invalid")
    normalized = unicodedata.normalize("NFC", narrative).casefold()
    normalized = " ".join(normalized.split())
    if not normalized:
        raise TemporalSplitError("split_narrative_contract_invalid")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def temporal_assignment(received: date) -> str:
    """Assign one approved split from an eligible receipt date."""

    if WINDOW_START <= received < TRAIN_END_EXCLUSIVE:
        return "train"
    if TRAIN_END_EXCLUSIVE <= received < VALIDATION_END_EXCLUSIVE:
        return "validation"
    if VALIDATION_END_EXCLUSIVE <= received < WINDOW_END_EXCLUSIVE:
        return "test"
    raise TemporalSplitError("split_date_outside_approved_window")


def build_temporal_split(
    run_manifest_path: Path,
    *,
    repository_root: Path = PROJECT_ROOT,
    settings: DatabaseSettings | None = None,
    lineage_reader: LineageReader = read_git_lineage,
) -> dict[str, Any]:
    """Build or verify one append-only split and publish aggregate evidence."""

    root = repository_root.resolve()
    manifest, manifest_bytes = _load_run_manifest(run_manifest_path, root)
    batch_ids = [str(shard["batch_id"]) for shard in manifest["shards"]]
    if len(set(batch_ids)) != len(batch_ids):
        raise TemporalSplitError("split_run_manifest_duplicate_batch")
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    database_settings = settings or DatabaseSettings.from_environment(env_file=root / ".env")

    try:
        with psycopg.connect(database_settings.psycopg_conninfo()) as connection:
            if _split_run_exists(connection, str(manifest["run_id"])):
                report = _database_report(
                    connection,
                    manifest=manifest,
                    manifest_sha256=manifest_sha256,
                    batch_ids=batch_ids,
                )
            else:
                commit_sha, working_tree_clean = lineage_reader(root)
                if not SHA40_PATTERN.fullmatch(commit_sha) or not working_tree_clean:
                    raise TemporalSplitError("split_requires_clean_commit")
                _prepare_candidates(
                    connection,
                    batch_ids,
                    expected_input_count=sum(
                        int(shard["returned_record_count"]) for shard in manifest["shards"]
                    ),
                )
                _classify_candidates(connection)
                _persist_split_run(
                    connection,
                    manifest=manifest,
                    manifest_sha256=manifest_sha256,
                    implementation_commit_sha=commit_sha,
                )
                report = _database_report(
                    connection,
                    manifest=manifest,
                    manifest_sha256=manifest_sha256,
                    batch_ids=batch_ids,
                )
    except TemporalSplitError:
        raise
    except psycopg.Error as error:
        raise TemporalSplitError("split_database_failed") from error

    schema = json.loads(SPLIT_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(report))
    if errors:
        raise TemporalSplitError("split_manifest_schema_invalid", issue_count=len(errors))
    report_path = (
        root
        / "data"
        / "manifests"
        / "cfpb"
        / "splits"
        / f"{manifest['run_id']}-split-{SPLIT_VERSION}.json"
    )
    _atomic_json(report_path, report)
    return report


def _load_run_manifest(path: Path, root: Path) -> tuple[dict[str, Any], bytes]:
    resolved = path.resolve()
    expected_parent = (root / "data" / "manifests" / "cfpb" / "runs").resolve()
    if resolved.parent != expected_parent:
        raise TemporalSplitError("unsafe_run_manifest_path")
    try:
        encoded = resolved.read_bytes()
        manifest = json.loads(encoded)
        schema = json.loads(RUN_SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TemporalSplitError("split_run_manifest_unreadable") from error
    if not isinstance(manifest, dict):
        raise TemporalSplitError("split_run_manifest_schema_invalid")
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(manifest)
    )
    if errors:
        raise TemporalSplitError("split_run_manifest_schema_invalid", issue_count=len(errors))
    return manifest, encoded


def _split_run_exists(connection: psycopg.Connection[Any], run_id: str) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM analytical.split_runs
        WHERE run_id = %s AND population_version = %s AND split_version = %s
        """,
        (run_id, POPULATION_VERSION, SPLIT_VERSION),
    ).fetchone()
    return row is not None


def _prepare_candidates(
    connection: psycopg.Connection[Any],
    batch_ids: Sequence[str],
    *,
    expected_input_count: int,
) -> None:
    run_counts = connection.execute(
        """
        SELECT count(*), coalesce(sum(input_record_count), 0),
               coalesce(sum(eligible_record_count), 0),
               coalesce(sum(excluded_record_count), 0),
               coalesce(sum(output_record_count), 0)
        FROM analytical.population_runs
        WHERE raw_batch_id = ANY(%s)
          AND staging_transformation_version = %s
          AND population_version = %s
        """,
        (list(batch_ids), TRANSFORMATION_VERSION, POPULATION_VERSION),
    ).fetchone()
    if (
        run_counts is None
        or int(run_counts[0]) != len(batch_ids)
        or int(run_counts[1]) != expected_input_count
        or int(run_counts[1]) != int(run_counts[4])
        or int(run_counts[2]) + int(run_counts[3]) != int(run_counts[4])
    ):
        raise TemporalSplitError("split_source_population_incomplete")
    source = connection.execute(
        """
        SELECT count(DISTINCT raw_batch_id), count(*)
        FROM analytical.population_outcomes
        WHERE raw_batch_id = ANY(%s)
          AND staging_transformation_version = %s
          AND population_version = %s
          AND eligibility_status = 'eligible'
        """,
        (list(batch_ids), TRANSFORMATION_VERSION, POPULATION_VERSION),
    ).fetchone()
    if (
        source is None
        or int(source[0]) != len(batch_ids)
        or int(source[1]) <= 0
        or int(source[1]) != int(run_counts[2])
    ):
        raise TemporalSplitError("split_source_population_incomplete")

    connection.execute(
        """
        CREATE TEMP TABLE split_candidates (
            raw_batch_id text NOT NULL,
            source_row_ordinal integer NOT NULL,
            date_received date NOT NULL,
            complaint_id text NOT NULL,
            target_product text NOT NULL,
            narrative_fingerprint_sha256 char(64) NOT NULL,
            PRIMARY KEY (raw_batch_id, source_row_ordinal)
        ) ON COMMIT DROP
        """
    )
    query = """
        SELECT s.raw_batch_id, s.source_row_ordinal, s.date_received,
               s.complaint_id, s.narrative, p.target_product
        FROM analytical.population_outcomes p
        JOIN staging.complaint_outcomes s
          ON s.raw_batch_id = p.raw_batch_id
         AND s.source_row_ordinal = p.source_row_ordinal
         AND s.transformation_version = p.staging_transformation_version
        WHERE p.raw_batch_id = ANY(%s)
          AND p.staging_transformation_version = %s
          AND p.population_version = %s
          AND p.eligibility_status = 'eligible'
        ORDER BY s.raw_batch_id, s.source_row_ordinal
    """
    inserted = 0
    with connection.cursor(name=f"split_source_{uuid.uuid4().hex}") as reader:
        reader.execute(query, (list(batch_ids), TRANSFORMATION_VERSION, POPULATION_VERSION))
        reader.itersize = FETCH_SIZE
        with connection.cursor() as writer:
            while rows := reader.fetchmany(FETCH_SIZE):
                candidates = []
                for row in rows:
                    if (
                        not isinstance(row[2], date)
                        or not isinstance(row[3], str)
                        or not isinstance(row[4], str)
                        or not isinstance(row[5], str)
                    ):
                        raise TemporalSplitError("split_source_contract_invalid")
                    temporal_assignment(row[2])
                    candidates.append((*row[:4], row[5], narrative_fingerprint(row[4])))
                writer.executemany(
                    """
                    INSERT INTO split_candidates (
                        raw_batch_id, source_row_ordinal, date_received,
                        complaint_id, target_product, narrative_fingerprint_sha256
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    candidates,
                )
                inserted += len(candidates)
    if inserted != int(source[1]):
        raise TemporalSplitError("split_candidate_count_mismatch")
    connection.execute(
        "CREATE INDEX ix_temp_split_fingerprint ON split_candidates (narrative_fingerprint_sha256)"
    )
    connection.execute("ANALYZE split_candidates")


def _classify_candidates(connection: psycopg.Connection[Any]) -> None:
    connection.execute(
        """
        CREATE TEMP TABLE split_classified ON COMMIT DROP AS
        WITH fingerprint_groups AS (
            SELECT narrative_fingerprint_sha256,
                   count(DISTINCT target_product) AS label_count
            FROM split_candidates
            GROUP BY narrative_fingerprint_sha256
        ), ranked AS (
            SELECT c.*, g.label_count,
                   row_number() OVER (
                       PARTITION BY c.narrative_fingerprint_sha256
                       ORDER BY c.date_received, c.complaint_id,
                                c.raw_batch_id, c.source_row_ordinal
                   ) AS canonical_rank
            FROM split_candidates c
            JOIN fingerprint_groups g USING (narrative_fingerprint_sha256)
        )
        SELECT raw_batch_id, source_row_ordinal, date_received, target_product,
               narrative_fingerprint_sha256,
               CASE WHEN label_count = 1 AND canonical_rank = 1
                    THEN 'included' ELSE 'excluded' END AS disposition,
               CASE WHEN label_count > 1 THEN 'duplicate_label_conflict'
                    WHEN canonical_rank > 1 THEN 'duplicate_same_label'
                    ELSE NULL END AS exclusion_reason,
               CASE WHEN label_count > 1 OR canonical_rank > 1 THEN NULL
                    WHEN date_received < DATE '2024-09-01' THEN 'train'
                    WHEN date_received < DATE '2024-11-01' THEN 'validation'
                    ELSE 'test' END AS split_assignment
        FROM ranked
        """
    )
    connection.execute(
        "CREATE UNIQUE INDEX ix_temp_split_classified_row "
        "ON split_classified (raw_batch_id, source_row_ordinal)"
    )
    connection.execute("ANALYZE split_classified")


def _persist_split_run(
    connection: psycopg.Connection[Any],
    *,
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    implementation_commit_sha: str,
) -> None:
    counts = connection.execute(
        """
        SELECT count(*),
               count(*) FILTER (WHERE disposition = 'included'),
               count(*) FILTER (WHERE exclusion_reason = 'duplicate_same_label'),
               count(*) FILTER (WHERE exclusion_reason = 'duplicate_label_conflict'),
               count(*) FILTER (WHERE split_assignment = 'train'),
               count(*) FILTER (WHERE split_assignment = 'validation'),
               count(*) FILTER (WHERE split_assignment = 'test')
        FROM split_classified
        """
    ).fetchone()
    if counts is None or any(int(value) < 0 for value in counts):
        raise TemporalSplitError("split_classification_missing")
    if int(counts[0]) != int(counts[1]) + int(counts[2]) + int(counts[3]):
        raise TemporalSplitError("split_dispositions_do_not_reconcile")
    if int(counts[1]) != int(counts[4]) + int(counts[5]) + int(counts[6]):
        raise TemporalSplitError("split_assignments_do_not_reconcile")
    if any(int(value) <= 0 for value in counts[4:7]):
        raise TemporalSplitError("split_assignment_empty")

    connection.execute(
        """
        INSERT INTO analytical.split_runs (
            run_id, staging_transformation_version, population_version,
            split_version, fingerprint_version, taxonomy_version,
            window_start, train_end_exclusive, validation_end_exclusive,
            window_end_exclusive, implementation_commit_sha,
            source_run_manifest_sha256, input_eligible_count,
            included_record_count, duplicate_same_label_count,
            duplicate_label_conflict_count, train_record_count,
            validation_record_count, test_record_count
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        """,
        (
            manifest["run_id"],
            TRANSFORMATION_VERSION,
            POPULATION_VERSION,
            SPLIT_VERSION,
            FINGERPRINT_VERSION,
            TAXONOMY_VERSION,
            WINDOW_START,
            TRAIN_END_EXCLUSIVE,
            VALIDATION_END_EXCLUSIVE,
            WINDOW_END_EXCLUSIVE,
            implementation_commit_sha,
            manifest_sha256,
            *[int(value) for value in counts],
        ),
    )
    connection.execute(
        """
        INSERT INTO analytical.split_outcomes (
            run_id, raw_batch_id, source_row_ordinal,
            staging_transformation_version, population_version, split_version,
            disposition, split_assignment, exclusion_reason,
            narrative_fingerprint_sha256
        )
        SELECT %s, raw_batch_id, source_row_ordinal, %s, %s, %s,
               disposition, split_assignment, exclusion_reason,
               narrative_fingerprint_sha256
        FROM split_classified
        """,
        (manifest["run_id"], TRANSFORMATION_VERSION, POPULATION_VERSION, SPLIT_VERSION),
    )


def _database_report(
    connection: psycopg.Connection[Any],
    *,
    manifest: Mapping[str, Any],
    manifest_sha256: str,
    batch_ids: Sequence[str],
) -> dict[str, Any]:
    run = connection.execute(
        """
        SELECT staging_transformation_version, population_version, split_version,
               fingerprint_version, taxonomy_version, window_start,
               train_end_exclusive, validation_end_exclusive, window_end_exclusive,
               implementation_commit_sha, source_run_manifest_sha256,
               input_eligible_count, included_record_count,
               duplicate_same_label_count, duplicate_label_conflict_count,
               train_record_count, validation_record_count, test_record_count,
               created_at
        FROM analytical.split_runs
        WHERE run_id = %s AND population_version = %s AND split_version = %s
        """,
        (manifest["run_id"], POPULATION_VERSION, SPLIT_VERSION),
    ).fetchone()
    if run is None:
        raise TemporalSplitError("split_run_missing")
    expected_identity = (
        TRANSFORMATION_VERSION,
        POPULATION_VERSION,
        SPLIT_VERSION,
        FINGERPRINT_VERSION,
        TAXONOMY_VERSION,
        WINDOW_START,
        TRAIN_END_EXCLUSIVE,
        VALIDATION_END_EXCLUSIVE,
        WINDOW_END_EXCLUSIVE,
    )
    if tuple(run[:9]) != expected_identity or str(run[10]) != manifest_sha256:
        raise TemporalSplitError("split_identity_conflict")

    outcome = connection.execute(
        """
        SELECT count(*),
               count(*) FILTER (WHERE disposition = 'included'),
               count(*) FILTER (WHERE exclusion_reason = 'duplicate_same_label'),
               count(*) FILTER (WHERE exclusion_reason = 'duplicate_label_conflict'),
               count(*) FILTER (WHERE split_assignment = 'train'),
               count(*) FILTER (WHERE split_assignment = 'validation'),
               count(*) FILTER (WHERE split_assignment = 'test'),
               count(DISTINCT narrative_fingerprint_sha256)
                   FILTER (WHERE disposition = 'included')
        FROM analytical.split_outcomes
        WHERE run_id = %s AND population_version = %s AND split_version = %s
        """,
        (manifest["run_id"], POPULATION_VERSION, SPLIT_VERSION),
    ).fetchone()
    source = connection.execute(
        """
        SELECT count(DISTINCT raw_batch_id), count(*)
        FROM analytical.population_outcomes
        WHERE raw_batch_id = ANY(%s)
          AND staging_transformation_version = %s
          AND population_version = %s
          AND eligibility_status = 'eligible'
        """,
        (list(batch_ids), TRANSFORMATION_VERSION, POPULATION_VERSION),
    ).fetchone()
    invalid_dates = connection.execute(
        """
        SELECT count(*)
        FROM analytical.split_outcomes o
        JOIN staging.complaint_outcomes s
          ON s.raw_batch_id = o.raw_batch_id
         AND s.source_row_ordinal = o.source_row_ordinal
         AND s.transformation_version = o.staging_transformation_version
        WHERE o.run_id = %s AND o.population_version = %s
          AND o.split_version = %s AND o.disposition = 'included'
          AND NOT (
              (o.split_assignment = 'train' AND s.date_received >= %s
               AND s.date_received < %s)
              OR (o.split_assignment = 'validation' AND s.date_received >= %s
                  AND s.date_received < %s)
              OR (o.split_assignment = 'test' AND s.date_received >= %s
                  AND s.date_received < %s)
          )
        """,
        (
            manifest["run_id"],
            POPULATION_VERSION,
            SPLIT_VERSION,
            WINDOW_START,
            TRAIN_END_EXCLUSIVE,
            TRAIN_END_EXCLUSIVE,
            VALIDATION_END_EXCLUSIVE,
            VALIDATION_END_EXCLUSIVE,
            WINDOW_END_EXCLUSIVE,
        ),
    ).fetchone()
    if outcome is None or source is None or invalid_dates is None:
        raise TemporalSplitError("split_reconciliation_missing")

    class_rows = connection.execute(
        """
        SELECT o.split_assignment, p.target_product, count(*)
        FROM analytical.split_outcomes o
        JOIN analytical.population_outcomes p
          ON p.raw_batch_id = o.raw_batch_id
         AND p.source_row_ordinal = o.source_row_ordinal
         AND p.staging_transformation_version = o.staging_transformation_version
         AND p.population_version = o.population_version
        WHERE o.run_id = %s AND o.population_version = %s
          AND o.split_version = %s AND o.disposition = 'included'
        GROUP BY o.split_assignment, p.target_product
        ORDER BY o.split_assignment, p.target_product
        """,
        (manifest["run_id"], POPULATION_VERSION, SPLIT_VERSION),
    ).fetchall()
    class_counts: dict[str, dict[str, int]] = {name: {} for name in ("train", "validation", "test")}
    for split_name, product, count in class_rows:
        class_counts[str(split_name)][str(product)] = int(count)

    stored_counts = tuple(int(value) for value in run[11:18])
    actual_counts = tuple(int(value) for value in outcome[:7])
    checks = {
        "source_population_reconciled": int(source[0]) == len(batch_ids)
        and int(source[1]) == stored_counts[0],
        "input_output_reconciled": actual_counts[0] == stored_counts[0],
        "dispositions_reconciled": actual_counts[0]
        == actual_counts[1] + actual_counts[2] + actual_counts[3],
        "assignments_reconciled": actual_counts[1]
        == actual_counts[4] + actual_counts[5] + actual_counts[6],
        "included_fingerprints_unique": actual_counts[1] == int(outcome[7]),
        "split_dates_valid": int(invalid_dates[0]) == 0,
        "all_splits_present": all(actual_counts[index] > 0 for index in (4, 5, 6)),
    }
    if actual_counts != stored_counts or not all(checks.values()):
        raise TemporalSplitError(
            "split_reconciliation_failed",
            failed_check_count=sum(not value for value in checks.values()),
        )
    created_at = run[18]
    return {
        "split_manifest_version": "1.0.0",
        "run_id": manifest["run_id"],
        "created_at_utc": created_at.isoformat().replace("+00:00", "Z"),
        "source": {
            "run_manifest_sha256": manifest_sha256,
            "extraction_commit_sha": manifest["lineage"]["code_commit_sha"],
            "split_implementation_commit_sha": str(run[9]),
        },
        "versions": {
            "staging_transformation": TRANSFORMATION_VERSION,
            "analytical_population": POPULATION_VERSION,
            "taxonomy": TAXONOMY_VERSION,
            "split": SPLIT_VERSION,
            "fingerprint": FINGERPRINT_VERSION,
        },
        "boundaries": {
            "window_start_inclusive": WINDOW_START.isoformat(),
            "train_end_exclusive": TRAIN_END_EXCLUSIVE.isoformat(),
            "validation_end_exclusive": VALIDATION_END_EXCLUSIVE.isoformat(),
            "window_end_exclusive": WINDOW_END_EXCLUSIVE.isoformat(),
        },
        "counts": {
            "input_eligible_count": actual_counts[0],
            "included_record_count": actual_counts[1],
            "excluded_record_count": actual_counts[2] + actual_counts[3],
            "output_record_count": actual_counts[0],
        },
        "exclusion_reason_counts": {
            "duplicate_same_label": actual_counts[2],
            "duplicate_label_conflict": actual_counts[3],
        },
        "split_counts": {
            "train": actual_counts[4],
            "validation": actual_counts[5],
            "test": actual_counts[6],
        },
        "class_counts_by_split": class_counts,
        "checks": checks,
        "privacy": {
            "contains_row_values": False,
            "contains_narratives": False,
            "contains_complaint_ids": False,
            "git_tracking_allowed": True,
        },
    }


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != encoded:
            raise TemporalSplitError("split_manifest_identity_conflict")
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
