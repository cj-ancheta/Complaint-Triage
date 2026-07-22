import hashlib
import json

import psycopg
import pytest
from psycopg.types.json import Jsonb

from complaint_triage.analytical_population import PopulationError, report_analytical_population
from complaint_triage.db import DatabaseSettings
from complaint_triage.staging import stage_raw_batch

BATCH_ID = "cfpb-20260722T000000Z-aaaaaaaaaaaa"


def _payload_sha256(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _insert_population_fixture(settings: DatabaseSettings) -> None:
    payloads = [
        {
            "complaint_id": "POP-1",
            "date_received": "2023-09-01",
            "complaint_what_happened": (
                "SYNTHETIC TEST RECORD. The customer disputes a fictional card charge."
            ),
            "product": "Credit card",
            "has_narrative": True,
        },
        {
            "complaint_id": "POP-2",
            "date_received": "2023-08-31",
            "complaint_what_happened": (
                "SYNTHETIC TEST RECORD. This fictional complaint is before the window."
            ),
            "product": "Debt collection",
            "has_narrative": True,
        },
        {
            "complaint_id": "POP-3",
            "date_received": "2024-01-02",
            "complaint_what_happened": (
                "SYNTHETIC TEST RECORD. This fictional complaint has an unknown product."
            ),
            "product": "SYNTHETIC PRODUCT OUTSIDE TAXONOMY",
            "has_narrative": True,
        },
        {
            "complaint_id": "POP-4",
            "date_received": "2024-01-02",
            "complaint_what_happened": (
                "REGISTRO DE PRUEBA SINTETICO. El cliente disputa un cargo desconocido."
            ),
            "product": "Checking or savings account",
            "has_narrative": True,
        },
        {
            "complaint_id": "POP-5",
            "date_received": "2024-01-02",
            "complaint_what_happened": "SYNTHETIC TEST RECORD. Quarantined source row.",
            "product": "Mortgage",
            "has_narrative": False,
        },
    ]
    with psycopg.connect(settings.psycopg_conninfo()) as connection:
        connection.execute(
            """
            INSERT INTO raw.ingestion_batches (
                batch_id, manifest_version, is_synthetic,
                request_fingerprint_sha256, artifact_sha256,
                artifact_relative_path, artifact_byte_count, retrieved_at,
                returned_record_count, inserted_record_count,
                retention_policy_id, manifest
            )
            VALUES (%s, '1.0.0', true, %s, %s, %s, 1, CURRENT_TIMESTAMP,
                    %s, %s, 'not-applicable-synthetic-fixture', %s)
            """,
            (
                BATCH_ID,
                "b" * 64,
                "a" * 64,
                "data/raw/test.json",
                len(payloads),
                len(payloads),
                Jsonb({}),
            ),
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO raw.complaints (
                    batch_id, source_row_ordinal, complaint_id,
                    source_record_sha256, payload
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (
                        BATCH_ID,
                        ordinal,
                        payload["complaint_id"],
                        _payload_sha256(payload),
                        Jsonb(payload),
                    )
                    for ordinal, payload in enumerate(payloads)
                ],
            )
    stage_raw_batch(BATCH_ID, settings=settings)


@pytest.mark.postgres
def test_population_report_is_atomic_idempotent_reconciled_and_append_only(
    migrated_database: DatabaseSettings,
) -> None:
    _insert_population_fixture(migrated_database)
    conninfo = migrated_database.psycopg_conninfo()

    with psycopg.connect(conninfo) as connection:
        connection.execute(
            """
            CREATE FUNCTION analytical.reject_second_population_outcome()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.source_row_ordinal = 1 THEN
                    RAISE EXCEPTION 'test-only rejection';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER reject_second_population_outcome
            BEFORE INSERT ON analytical.population_outcomes
            FOR EACH ROW EXECUTE FUNCTION analytical.reject_second_population_outcome()
            """
        )

    with pytest.raises(PopulationError) as raised:
        report_analytical_population(BATCH_ID, settings=migrated_database)
    assert raised.value.code == "database_write_failed"

    with psycopg.connect(conninfo) as connection:
        assert connection.execute("SELECT count(*) FROM analytical.population_runs").fetchone() == (
            0,
        )
        assert connection.execute(
            "SELECT count(*) FROM analytical.population_outcomes"
        ).fetchone() == (0,)
        connection.execute(
            "DROP TRIGGER reject_second_population_outcome ON analytical.population_outcomes"
        )
        connection.execute("DROP FUNCTION analytical.reject_second_population_outcome()")

    first = report_analytical_population(BATCH_ID, settings=migrated_database)
    second = report_analytical_population(BATCH_ID, settings=migrated_database)

    assert first["status"] == "reported"
    assert second["status"] == "already_reported"
    assert (
        first["counts"]
        == second["counts"]
        == {
            "input_record_count": 5,
            "eligible_record_count": 1,
            "excluded_record_count": 4,
            "output_record_count": 5,
        }
    )
    assert first["exclusion_reason_counts"] == {
        "date_before_window": 1,
        "language_not_english": 1,
        "product_outside_taxonomy": 1,
        "staging_quarantined": 1,
    }
    assert first["eligible_counts_by_product"] == {"Credit card": 1}
    assert first["detected_language_counts"] == {"en": 1, "es": 1}
    assert first["checks"] == {
        "input_output_reconciled": True,
        "statuses_reconciled": True,
    }
    assert first["privacy"]["narratives_in_report"] is False

    with psycopg.connect(conninfo) as connection:
        stored = connection.execute(
            """
            SELECT eligibility_status, count(*)
            FROM analytical.population_outcomes
            GROUP BY eligibility_status
            ORDER BY eligibility_status
            """
        ).fetchall()
        assert stored == [("eligible", 1), ("excluded", 4)]

        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO analytical.population_outcomes (
                    raw_batch_id, source_row_ordinal,
                    staging_transformation_version, population_version,
                    eligibility_status, exclusion_reasons
                )
                VALUES (%s, 0, '1.0.0', 'test-invalid-reason',
                        'excluded', ARRAY['unknown_reason'])
                """,
                (BATCH_ID,),
            )
        connection.rollback()

        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO analytical.population_outcomes (
                    raw_batch_id, source_row_ordinal,
                    staging_transformation_version, population_version,
                    eligibility_status, exclusion_reasons, target_product,
                    detected_language, narrative_char_count
                )
                VALUES (%s, 0, '1.0.0', 'test-invalid-target',
                        'eligible', ARRAY[]::text[], 'Invented product', 'en', 10)
                """,
                (BATCH_ID,),
            )
        connection.rollback()

        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            connection.execute("UPDATE analytical.population_outcomes SET detected_language = 'fr'")
        connection.rollback()
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            connection.execute("DELETE FROM analytical.population_runs")
