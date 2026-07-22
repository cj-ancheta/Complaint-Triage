"""Versioned analytical-population eligibility with aggregate-only reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from typing import Any, Protocol

import psycopg
from lingua import LanguageDetectorBuilder

from complaint_triage.db import DatabaseSettings
from complaint_triage.staging import BATCH_ID_PATTERN, TRANSFORMATION_VERSION
from complaint_triage.taxonomy import (
    CURRENT_PRODUCT_LABELS,
    MODELLING_WINDOW_END_EXCLUSIVE,
    MODELLING_WINDOW_START,
    TAXONOMY_VERSION,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
POPULATION_VERSION = "1.0.0"
WINDOW_START = date.fromisoformat(MODELLING_WINDOW_START)
WINDOW_END_EXCLUSIVE = date.fromisoformat(MODELLING_WINDOW_END_EXCLUSIVE)
LANGUAGE_DETECTOR_ID = f"lingua-{version('lingua-language-detector')}-all-languages-high-accuracy"
FETCH_BATCH_SIZE = 1_000


class PopulationExclusionReason(StrEnum):
    STAGING_QUARANTINED = "staging_quarantined"
    DATE_BEFORE_WINDOW = "date_before_window"
    DATE_AT_OR_AFTER_WINDOW_END = "date_at_or_after_window_end"
    PRODUCT_OUTSIDE_TAXONOMY = "product_outside_taxonomy"
    LANGUAGE_NOT_ENGLISH = "language_not_english"
    LANGUAGE_UNDETERMINED = "language_undetermined"


class PopulationError(Exception):
    """A controlled population-report failure containing no narrative text."""

    def __init__(self, code: str, **details: str | int | bool | None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class StagedPopulationRow:
    raw_batch_id: str
    source_row_ordinal: int
    transformation_version: str
    outcome_status: str
    date_received: date | None
    narrative: str | None
    product_raw: str | None


@dataclass(frozen=True)
class PopulationOutcome:
    raw_batch_id: str
    source_row_ordinal: int
    staging_transformation_version: str
    eligibility_status: str
    exclusion_reasons: tuple[str, ...]
    target_product: str | None
    detected_language: str | None
    narrative_char_count: int | None


class LanguageIdentifier(Protocol):
    def __call__(self, text: str) -> str | None: ...


def safe_population_error(error: PopulationError) -> dict[str, Any]:
    return {
        "status": "error",
        "error": {"code": error.code, **error.details},
        "privacy": {
            "narratives_logged": False,
            "narratives_in_report": False,
            "narratives_copied_to_analytical": False,
        },
    }


@lru_cache(maxsize=1)
def _language_detector() -> Any:
    return LanguageDetectorBuilder.from_all_languages().build()


def identify_language(text: str) -> str | None:
    """Return a lower-case ISO 639-1 language code, or None if undetermined."""

    detected = _language_detector().detect_language_of(text)
    return None if detected is None else detected.iso_code_639_1.name.lower()


def assess_population_rows(
    rows: tuple[StagedPopulationRow, ...],
    *,
    language_identifier: LanguageIdentifier = identify_language,
) -> tuple[PopulationOutcome, ...]:
    """Assign deterministic eligibility outcomes without retaining narrative text."""

    outcomes: list[PopulationOutcome] = []
    for row in rows:
        if row.transformation_version != TRANSFORMATION_VERSION:
            raise PopulationError(
                "staging_transformation_version_unsupported",
                source_row_ordinal=row.source_row_ordinal,
            )
        if row.outcome_status not in {"accepted", "quarantined"}:
            raise PopulationError(
                "staging_contract_violation",
                source_row_ordinal=row.source_row_ordinal,
            )
        if row.outcome_status == "quarantined":
            outcomes.append(
                _outcome(
                    row,
                    reasons=(PopulationExclusionReason.STAGING_QUARANTINED,),
                    target_product=None,
                    detected_language=None,
                    narrative_char_count=None,
                )
            )
            continue
        if row.date_received is None or row.narrative is None or row.product_raw is None:
            raise PopulationError(
                "staging_contract_violation",
                source_row_ordinal=row.source_row_ordinal,
            )

        reasons: list[PopulationExclusionReason] = []
        if row.date_received < WINDOW_START:
            reasons.append(PopulationExclusionReason.DATE_BEFORE_WINDOW)
        elif row.date_received >= WINDOW_END_EXCLUSIVE:
            reasons.append(PopulationExclusionReason.DATE_AT_OR_AFTER_WINDOW_END)
        if row.product_raw not in CURRENT_PRODUCT_LABELS:
            reasons.append(PopulationExclusionReason.PRODUCT_OUTSIDE_TAXONOMY)

        detected_language: str | None = None
        if not reasons:
            try:
                detected_language = language_identifier(row.narrative)
            except Exception as error:
                raise PopulationError(
                    "language_detection_failed",
                    source_row_ordinal=row.source_row_ordinal,
                ) from error
            if detected_language is None:
                reasons.append(PopulationExclusionReason.LANGUAGE_UNDETERMINED)
            elif detected_language != "en":
                reasons.append(PopulationExclusionReason.LANGUAGE_NOT_ENGLISH)

        eligible = not reasons
        outcomes.append(
            _outcome(
                row,
                reasons=tuple(reasons),
                target_product=row.product_raw if eligible else None,
                detected_language=detected_language,
                narrative_char_count=len(row.narrative),
            )
        )
    return tuple(outcomes)


def report_analytical_population(
    raw_batch_id: str,
    *,
    settings: DatabaseSettings | None = None,
    repository_root: Path = PROJECT_ROOT,
    population_version: str = POPULATION_VERSION,
) -> dict[str, Any]:
    """Persist immutable row outcomes and return an aggregate-only report."""

    if not BATCH_ID_PATTERN.fullmatch(raw_batch_id):
        raise PopulationError("batch_id_invalid")
    if population_version != POPULATION_VERSION:
        raise PopulationError("population_version_unsupported")
    database_settings = settings or DatabaseSettings.from_environment(
        env_file=repository_root / ".env"
    )

    try:
        with psycopg.connect(database_settings.psycopg_conninfo()) as connection:
            with connection.cursor() as cursor:
                expected_count = _load_expected_count(cursor, raw_batch_id)
                if _run_exists(cursor, raw_batch_id):
                    _verify_existing_run(cursor, raw_batch_id, expected_count)
                    return _stored_report(
                        cursor,
                        raw_batch_id,
                        status="already_reported",
                    )

            eligible_count = 0
            excluded_count = 0
            output_count = 0
            with connection.cursor(name="population_input") as read_cursor:
                read_cursor.execute(
                    """
                    SELECT raw_batch_id, source_row_ordinal, transformation_version,
                           outcome_status, date_received,
                           CASE WHEN outcome_status = 'accepted' THEN narrative END,
                           product_raw
                    FROM staging.complaint_outcomes
                    WHERE raw_batch_id = %s AND transformation_version = %s
                    ORDER BY source_row_ordinal
                    """,
                    (raw_batch_id, TRANSFORMATION_VERSION),
                )
                with connection.cursor() as write_cursor:
                    while values := read_cursor.fetchmany(FETCH_BATCH_SIZE):
                        rows = tuple(
                            StagedPopulationRow(
                                raw_batch_id=value[0],
                                source_row_ordinal=value[1],
                                transformation_version=value[2],
                                outcome_status=value[3],
                                date_received=value[4],
                                narrative=value[5],
                                product_raw=value[6],
                            )
                            for value in values
                        )
                        outcomes = assess_population_rows(
                            rows,
                            language_identifier=identify_language,
                        )
                        eligible_count += sum(
                            outcome.eligibility_status == "eligible" for outcome in outcomes
                        )
                        excluded_count += sum(
                            outcome.eligibility_status == "excluded" for outcome in outcomes
                        )
                        output_count += len(outcomes)
                        _insert_outcomes(write_cursor, outcomes)

                    if output_count != expected_count:
                        raise PopulationError("population_input_reconciliation_failed")
                    write_cursor.execute(
                        """
                        INSERT INTO analytical.population_runs (
                            raw_batch_id,
                            staging_transformation_version,
                            population_version,
                            taxonomy_version,
                            window_start,
                            window_end_exclusive,
                            language_detector,
                            input_record_count,
                            eligible_record_count,
                            excluded_record_count,
                            output_record_count
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            raw_batch_id,
                            TRANSFORMATION_VERSION,
                            POPULATION_VERSION,
                            TAXONOMY_VERSION,
                            WINDOW_START,
                            WINDOW_END_EXCLUSIVE,
                            LANGUAGE_DETECTOR_ID,
                            expected_count,
                            eligible_count,
                            excluded_count,
                            output_count,
                        ),
                    )
                    return _stored_report(write_cursor, raw_batch_id, status="reported")
    except PopulationError:
        raise
    except psycopg.Error as error:
        raise PopulationError("database_write_failed") from error


def _outcome(
    row: StagedPopulationRow,
    *,
    reasons: tuple[PopulationExclusionReason, ...],
    target_product: str | None,
    detected_language: str | None,
    narrative_char_count: int | None,
) -> PopulationOutcome:
    return PopulationOutcome(
        raw_batch_id=row.raw_batch_id,
        source_row_ordinal=row.source_row_ordinal,
        staging_transformation_version=row.transformation_version,
        eligibility_status="excluded" if reasons else "eligible",
        exclusion_reasons=tuple(reason.value for reason in reasons),
        target_product=target_product,
        detected_language=detected_language,
        narrative_char_count=narrative_char_count,
    )


def _load_expected_count(cursor: psycopg.Cursor[Any], raw_batch_id: str) -> int:
    cursor.execute(
        """
        SELECT input_record_count
        FROM staging.transformation_batches
        WHERE raw_batch_id = %s AND transformation_version = %s
        """,
        (raw_batch_id, TRANSFORMATION_VERSION),
    )
    row = cursor.fetchone()
    if row is None:
        raise PopulationError("staging_batch_not_found")
    return int(row[0])


def _run_exists(cursor: psycopg.Cursor[Any], raw_batch_id: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM analytical.population_runs
        WHERE raw_batch_id = %s
          AND staging_transformation_version = %s
          AND population_version = %s
        """,
        (raw_batch_id, TRANSFORMATION_VERSION, POPULATION_VERSION),
    )
    return cursor.fetchone() is not None


def _verify_existing_run(
    cursor: psycopg.Cursor[Any], raw_batch_id: str, expected_count: int
) -> None:
    cursor.execute(
        """
        SELECT taxonomy_version, window_start, window_end_exclusive,
               language_detector, input_record_count,
               eligible_record_count + excluded_record_count,
               output_record_count,
               (
                   SELECT count(*)
                   FROM analytical.population_outcomes
                   WHERE raw_batch_id = %s
                     AND staging_transformation_version = %s
                     AND population_version = %s
               )
        FROM analytical.population_runs
        WHERE raw_batch_id = %s
          AND staging_transformation_version = %s
          AND population_version = %s
        """,
        (
            raw_batch_id,
            TRANSFORMATION_VERSION,
            POPULATION_VERSION,
            raw_batch_id,
            TRANSFORMATION_VERSION,
            POPULATION_VERSION,
        ),
    )
    row = cursor.fetchone()
    expected = (
        TAXONOMY_VERSION,
        WINDOW_START,
        WINDOW_END_EXCLUSIVE,
        LANGUAGE_DETECTOR_ID,
        expected_count,
        expected_count,
        expected_count,
        expected_count,
    )
    if row is None or tuple(row) != expected:
        raise PopulationError("population_identity_conflict")


def _insert_outcomes(cursor: psycopg.Cursor[Any], outcomes: tuple[PopulationOutcome, ...]) -> None:
    cursor.executemany(
        """
        INSERT INTO analytical.population_outcomes (
            raw_batch_id,
            source_row_ordinal,
            staging_transformation_version,
            population_version,
            eligibility_status,
            exclusion_reasons,
            target_product,
            detected_language,
            narrative_char_count
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            (
                outcome.raw_batch_id,
                outcome.source_row_ordinal,
                outcome.staging_transformation_version,
                POPULATION_VERSION,
                outcome.eligibility_status,
                list(outcome.exclusion_reasons),
                outcome.target_product,
                outcome.detected_language,
                outcome.narrative_char_count,
            )
            for outcome in outcomes
        ],
    )


def _stored_report(
    cursor: psycopg.Cursor[Any], raw_batch_id: str, *, status: str
) -> dict[str, Any]:
    identity = (raw_batch_id, TRANSFORMATION_VERSION, POPULATION_VERSION)
    cursor.execute(
        """
        SELECT input_record_count, eligible_record_count,
               excluded_record_count, output_record_count
        FROM analytical.population_runs
        WHERE raw_batch_id = %s
          AND staging_transformation_version = %s
          AND population_version = %s
        """,
        identity,
    )
    counts = cursor.fetchone()
    if counts is None:
        raise PopulationError("population_identity_conflict")

    cursor.execute(
        """
        SELECT reason, count(*)
        FROM analytical.population_outcomes,
             unnest(exclusion_reasons) AS reason
        WHERE raw_batch_id = %s
          AND staging_transformation_version = %s
          AND population_version = %s
        GROUP BY reason
        ORDER BY reason
        """,
        identity,
    )
    exclusion_counts = {row[0]: row[1] for row in cursor.fetchall()}
    cursor.execute(
        """
        SELECT target_product, count(*)
        FROM analytical.population_outcomes
        WHERE raw_batch_id = %s
          AND staging_transformation_version = %s
          AND population_version = %s
          AND eligibility_status = 'eligible'
        GROUP BY target_product
        ORDER BY target_product
        """,
        identity,
    )
    product_counts = {row[0]: row[1] for row in cursor.fetchall()}
    cursor.execute(
        """
        SELECT detected_language, count(*)
        FROM analytical.population_outcomes
        WHERE raw_batch_id = %s
          AND staging_transformation_version = %s
          AND population_version = %s
          AND detected_language IS NOT NULL
        GROUP BY detected_language
        ORDER BY detected_language
        """,
        identity,
    )
    language_counts = {row[0].strip(): row[1] for row in cursor.fetchall()}
    cursor.execute(
        """
        SELECT min(narrative_char_count), max(narrative_char_count),
               avg(narrative_char_count)
        FROM analytical.population_outcomes
        WHERE raw_batch_id = %s
          AND staging_transformation_version = %s
          AND population_version = %s
          AND eligibility_status = 'eligible'
        """,
        identity,
    )
    length_values = cursor.fetchone()
    language_evaluated_count = sum(language_counts.values()) + exclusion_counts.get(
        PopulationExclusionReason.LANGUAGE_UNDETERMINED.value,
        0,
    )
    return {
        "status": status,
        "raw_batch_id": raw_batch_id,
        "staging_transformation_version": TRANSFORMATION_VERSION,
        "population_version": POPULATION_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "window": {
            "date_received_min": MODELLING_WINDOW_START,
            "date_received_max_exclusive": MODELLING_WINDOW_END_EXCLUSIVE,
        },
        "language_detector": LANGUAGE_DETECTOR_ID,
        "counts": {
            "input_record_count": counts[0],
            "eligible_record_count": counts[1],
            "excluded_record_count": counts[2],
            "output_record_count": counts[3],
        },
        "exclusion_reason_counts": exclusion_counts,
        "eligible_counts_by_product": product_counts,
        "detected_language_counts": language_counts,
        "language_evaluated_record_count": language_evaluated_count,
        "eligible_narrative_length": {
            "minimum": length_values[0],
            "maximum": length_values[1],
            "mean": round(float(length_values[2]), 3) if length_values[2] is not None else None,
        },
        "checks": {
            "input_output_reconciled": counts[0] == counts[3],
            "statuses_reconciled": counts[1] + counts[2] == counts[3],
        },
        "privacy": {
            "narratives_read_for_language_detection": language_evaluated_count > 0,
            "narratives_logged": False,
            "narratives_in_report": False,
            "narratives_copied_to_analytical": False,
        },
    }
