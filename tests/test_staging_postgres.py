import json
import shutil
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from complaint_triage.db import DatabaseSettings
from complaint_triage.raw_ingestion import ingest_raw_batch
from complaint_triage.staging import QuarantineReason, StagingError, stage_raw_batch

REPOSITORY_ROOT = Path(__file__).parents[1]
MANIFEST_FIXTURE = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "cfpb" / "raw_batch_manifest_synthetic.json"
)
ARTIFACT_FIXTURE = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "cfpb" / "search_response_synthetic.json"
)


def _stage_fixture_files(tmp_path: Path) -> tuple[Path, str]:
    manifest = json.loads(MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "data" / "manifests" / "cfpb" / "batch.json"
    artifact_path = tmp_path / Path(*Path(manifest["artifact"]["relative_path"]).parts)
    manifest_path.parent.mkdir(parents=True)
    artifact_path.parent.mkdir(parents=True)
    shutil.copyfile(MANIFEST_FIXTURE, manifest_path)
    shutil.copyfile(ARTIFACT_FIXTURE, artifact_path)
    return manifest_path, manifest["batch_id"]


@pytest.mark.postgres
def test_staging_is_atomic_idempotent_reconciled_and_append_only(
    tmp_path: Path, migrated_database: DatabaseSettings
) -> None:
    manifest_path, batch_id = _stage_fixture_files(tmp_path)
    ingest_raw_batch(manifest_path, repository_root=tmp_path, settings=migrated_database)
    conninfo = migrated_database.psycopg_conninfo()

    with psycopg.connect(conninfo) as connection:
        connection.execute(
            """
            CREATE FUNCTION staging.reject_second_outcome()
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
            CREATE TRIGGER reject_second_outcome
            BEFORE INSERT ON staging.complaint_outcomes
            FOR EACH ROW EXECUTE FUNCTION staging.reject_second_outcome()
            """
        )

    with pytest.raises(StagingError) as raised:
        stage_raw_batch(batch_id, settings=migrated_database)
    assert raised.value.code == "database_write_failed"

    with psycopg.connect(conninfo) as connection:
        assert connection.execute(
            "SELECT count(*) FROM staging.transformation_batches"
        ).fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM staging.complaint_outcomes").fetchone() == (
            0,
        )
        connection.execute("DROP TRIGGER reject_second_outcome ON staging.complaint_outcomes")
        connection.execute("DROP FUNCTION staging.reject_second_outcome()")

    first = stage_raw_batch(batch_id, settings=migrated_database)
    second = stage_raw_batch(batch_id, settings=migrated_database)

    assert first["status"] == "staged"
    assert first["input_record_count"] == 3
    assert first["accepted_record_count"] == 3
    assert first["quarantined_record_count"] == 0
    assert first["inserted_record_count"] == 3
    assert second["status"] == "already_staged"
    assert second["inserted_record_count"] == 0

    with psycopg.connect(conninfo) as connection:
        counts = connection.execute(
            """
            SELECT input_record_count, accepted_record_count,
                   quarantined_record_count, output_record_count
            FROM staging.transformation_batches
            """
        ).fetchone()
        statuses = connection.execute(
            """
            SELECT outcome_status, count(*)
            FROM staging.complaint_outcomes
            GROUP BY outcome_status
            """
        ).fetchall()
        assert counts == (3, 3, 0, 3)
        assert statuses == [("accepted", 3)]

        connection.execute(
            """
            INSERT INTO staging.transformation_batches (
                raw_batch_id, transformation_version, input_record_count,
                accepted_record_count, quarantined_record_count, output_record_count
            )
            VALUES (%s, 'test-unknown-reason', 3, 2, 1, 3)
            """,
            (batch_id,),
        )
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """
                INSERT INTO staging.complaint_outcomes (
                    raw_batch_id, source_row_ordinal, transformation_version,
                    source_record_sha256, outcome_status, quarantine_reasons
                )
                SELECT batch_id, source_row_ordinal, 'test-unknown-reason',
                       source_record_sha256, 'quarantined', ARRAY['unknown_reason']
                FROM raw.complaints
                WHERE batch_id = %s AND source_row_ordinal = 0
                """,
                (batch_id,),
            )
        connection.rollback()

        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            connection.execute("UPDATE staging.complaint_outcomes SET product_raw = 'changed'")
        connection.rollback()
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            connection.execute("DELETE FROM staging.transformation_batches")


@pytest.mark.postgres
def test_quarantined_rows_are_stored_and_reconciled(
    migrated_database: DatabaseSettings,
) -> None:
    batch_id = "cfpb-20260722T000000Z-aaaaaaaaaaaa"
    conninfo = migrated_database.psycopg_conninfo()
    with psycopg.connect(conninfo) as connection:
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
                    2, 2, 'not-applicable-synthetic-fixture', %s)
            """,
            (batch_id, "b" * 64, "a" * 64, "data/raw/test.json", Jsonb({})),
        )
        payloads = [
            {
                "complaint_id": "DUP-1",
                "date_received": "not-a-date",
                "complaint_what_happened": "",
                "product": "",
                "has_narrative": False,
            },
            {
                "complaint_id": "DUP-1",
                "date_received": "2024-01-02",
                "complaint_what_happened": "Synthetic non-sensitive test narrative.",
                "product": "Synthetic product",
                "has_narrative": True,
            },
        ]
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
                    (batch_id, ordinal, "DUP-1", str(ordinal) * 64, Jsonb(payload))
                    for ordinal, payload in enumerate(payloads)
                ],
            )

    result = stage_raw_batch(batch_id, settings=migrated_database)

    assert result["input_record_count"] == 2
    assert result["accepted_record_count"] == 0
    assert result["quarantined_record_count"] == 2
    with psycopg.connect(conninfo) as connection:
        rows = connection.execute(
            """
            SELECT source_row_ordinal, quarantine_reasons
            FROM staging.complaint_outcomes
            ORDER BY source_row_ordinal
            """
        ).fetchall()
    assert QuarantineReason.DUPLICATE_COMPLAINT_ID.value in rows[0][1]
    assert QuarantineReason.SOURCE_RECORD_CHECKSUM_MISMATCH.value in rows[0][1]
    assert QuarantineReason.DATE_RECEIVED_INVALID.value in rows[0][1]
    assert QuarantineReason.NARRATIVE_INVALID.value in rows[0][1]
    assert QuarantineReason.PRODUCT_INVALID.value in rows[0][1]
    assert QuarantineReason.HAS_NARRATIVE_NOT_TRUE.value in rows[0][1]
    assert rows[1][1] == [
        QuarantineReason.SOURCE_RECORD_CHECKSUM_MISMATCH.value,
        QuarantineReason.DUPLICATE_COMPLAINT_ID.value,
    ]
