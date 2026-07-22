import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import psycopg
import pytest
from psycopg.types.json import Jsonb

from complaint_triage.analytical_population import POPULATION_VERSION
from complaint_triage.db import DatabaseSettings
from complaint_triage.real_extraction import (
    ExtractionContext,
    PublishedShard,
    approved_monthly_shards,
    publish_run_manifest,
)
from complaint_triage.staging import TRANSFORMATION_VERSION
from complaint_triage.taxonomy import CURRENT_PRODUCT_LABELS, TAXONOMY_VERSION
from complaint_triage.temporal_split import TemporalSplitError, build_temporal_split

RUN_ID = "cfpb-run-20260723T010000Z-aaaaaaaaaaaa"
COMMIT_SHA = "b" * 40


@dataclass(frozen=True)
class SyntheticRow:
    complaint_id: str
    received: date
    narrative: str
    product: str


def _fixture_rows() -> list[list[SyntheticRow]]:
    rows: list[list[SyntheticRow]] = []
    products = tuple(sorted(CURRENT_PRODUCT_LABELS))
    for index, spec in enumerate(approved_monthly_shards()):
        rows.append(
            [
                SyntheticRow(
                    complaint_id=f"SYNTHETIC-UNIQUE-{index:02d}",
                    received=date.fromisoformat(spec.start_inclusive),
                    narrative=f"Unique synthetic complaint narrative number {index}.",
                    product=products[index % len(products)],
                )
            ]
        )
    rows[1].append(
        SyntheticRow(
            "SYNTHETIC-DUPLICATE-TRAIN",
            date(2023, 10, 15),
            "Repeated whitespace narrative",
            "Credit card",
        )
    )
    rows[12].append(
        SyntheticRow(
            "SYNTHETIC-DUPLICATE-VALIDATION",
            date(2024, 9, 15),
            " REPEATED   whitespace\nNARRATIVE ",
            "Credit card",
        )
    )
    rows[14].append(
        SyntheticRow(
            "SYNTHETIC-DUPLICATE-TEST",
            date(2024, 11, 15),
            "repeated whitespace narrative",
            "Credit card",
        )
    )
    rows[5].append(
        SyntheticRow(
            "SYNTHETIC-CONFLICT-TRAIN",
            date(2024, 2, 15),
            "Conflicting label narrative",
            "Credit card",
        )
    )
    rows[15].append(
        SyntheticRow(
            "SYNTHETIC-CONFLICT-TEST",
            date(2024, 12, 15),
            " CONFLICTING  LABEL narrative ",
            "Debt collection",
        )
    )
    return rows


def _publish_manifest(tmp_path: Path, rows: list[list[SyntheticRow]]) -> tuple[Path, list[str]]:
    published = []
    batch_ids = []
    for index, (spec, batch_rows) in enumerate(zip(approved_monthly_shards(), rows, strict=True)):
        digest = hashlib.sha256(spec.month.encode()).hexdigest()
        batch_id = f"cfpb-20260723T{index:02d}0000Z-{digest[:12]}"
        batch_ids.append(batch_id)
        published.append(
            PublishedShard(
                ordinal=spec.ordinal,
                month=spec.month,
                start_inclusive=spec.start_inclusive,
                end_exclusive=spec.end_exclusive,
                api_date_received_min=spec.api_date_received_min,
                api_date_received_max=spec.api_date_received_max,
                preflight_count=len(batch_rows),
                batch_id=batch_id,
                manifest_relative_path=f"data/manifests/cfpb/{batch_id}.json",
                artifact_relative_path=f"data/raw/cfpb/sha256/{digest[:2]}/{digest}.json",
                artifact_sha256=digest,
                artifact_byte_count=100,
                returned_record_count=len(batch_rows),
            )
        )
    context = ExtractionContext(
        run_id=RUN_ID,
        retrieved_at_utc=datetime(2026, 7, 23, 1, tzinfo=UTC),
        expires_at_utc=datetime(2026, 11, 19, 15, 59, 59, tzinfo=UTC),
        code_commit_sha="a" * 40,
        working_tree_clean=True,
    )
    return (
        publish_run_manifest(published, context=context, repository_root=tmp_path),
        batch_ids,
    )


def _payload_sha256(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _insert_fixture(
    settings: DatabaseSettings, batch_ids: list[str], rows: list[list[SyntheticRow]]
) -> None:
    with psycopg.connect(settings.psycopg_conninfo()) as connection:
        for batch_id, batch_rows in zip(batch_ids, rows, strict=True):
            artifact_sha = hashlib.sha256(batch_id.encode()).hexdigest()
            connection.execute(
                """
                INSERT INTO raw.ingestion_batches (
                    batch_id, manifest_version, is_synthetic,
                    request_fingerprint_sha256, artifact_sha256,
                    artifact_relative_path, artifact_byte_count, retrieved_at,
                    returned_record_count, inserted_record_count,
                    retention_policy_id, manifest
                ) VALUES (%s, '1.0.0', true, %s, %s, %s, 100,
                          CURRENT_TIMESTAMP, %s, %s,
                          'not-applicable-synthetic-fixture', %s)
                """,
                (
                    batch_id,
                    hashlib.sha256(f"request-{batch_id}".encode()).hexdigest(),
                    artifact_sha,
                    f"data/raw/cfpb/sha256/{artifact_sha[:2]}/{artifact_sha}.json",
                    len(batch_rows),
                    len(batch_rows),
                    Jsonb({}),
                ),
            )
            raw_values = []
            staging_values = []
            population_values = []
            for ordinal, row in enumerate(batch_rows):
                payload = {
                    "complaint_id": row.complaint_id,
                    "date_received": row.received.isoformat(),
                    "complaint_what_happened": row.narrative,
                    "product": row.product,
                }
                raw_values.append(
                    (batch_id, ordinal, row.complaint_id, _payload_sha256(payload), Jsonb(payload))
                )
                staging_values.append(
                    (
                        batch_id,
                        ordinal,
                        TRANSFORMATION_VERSION,
                        _payload_sha256(payload),
                        row.complaint_id,
                        row.received,
                        row.narrative,
                        hashlib.sha256(row.narrative.encode()).hexdigest(),
                        row.product,
                    )
                )
                population_values.append(
                    (
                        batch_id,
                        ordinal,
                        TRANSFORMATION_VERSION,
                        POPULATION_VERSION,
                        row.product,
                        len(row.narrative),
                    )
                )
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO raw.complaints (
                        batch_id, source_row_ordinal, complaint_id,
                        source_record_sha256, payload
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    raw_values,
                )
            connection.execute(
                """
                INSERT INTO staging.transformation_batches (
                    raw_batch_id, transformation_version, input_record_count,
                    accepted_record_count, quarantined_record_count,
                    output_record_count
                ) VALUES (%s, %s, %s, %s, 0, %s)
                """,
                (
                    batch_id,
                    TRANSFORMATION_VERSION,
                    len(batch_rows),
                    len(batch_rows),
                    len(batch_rows),
                ),
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO staging.complaint_outcomes (
                        raw_batch_id, source_row_ordinal, transformation_version,
                        source_record_sha256, outcome_status, quarantine_reasons,
                        complaint_id, date_received, narrative, narrative_sha256,
                        product_raw
                    ) VALUES (%s, %s, %s, %s, 'accepted', ARRAY[]::text[],
                              %s, %s, %s, %s, %s)
                    """,
                    staging_values,
                )
            connection.execute(
                """
                INSERT INTO analytical.population_runs (
                    raw_batch_id, staging_transformation_version,
                    population_version, taxonomy_version, window_start,
                    window_end_exclusive, language_detector,
                    input_record_count, eligible_record_count,
                    excluded_record_count, output_record_count
                ) VALUES (%s, %s, %s, %s, DATE '2023-09-01',
                          DATE '2025-01-01', 'synthetic-test-detector',
                          %s, %s, 0, %s)
                """,
                (
                    batch_id,
                    TRANSFORMATION_VERSION,
                    POPULATION_VERSION,
                    TAXONOMY_VERSION,
                    len(batch_rows),
                    len(batch_rows),
                    len(batch_rows),
                ),
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO analytical.population_outcomes (
                        raw_batch_id, source_row_ordinal,
                        staging_transformation_version, population_version,
                        eligibility_status, exclusion_reasons, target_product,
                        detected_language, narrative_char_count
                    ) VALUES (%s, %s, %s, %s, 'eligible', ARRAY[]::text[],
                              %s, 'en', %s)
                    """,
                    population_values,
                )


@pytest.mark.postgres
def test_split_is_normalized_leakage_free_idempotent_and_append_only(
    migrated_database: DatabaseSettings, tmp_path: Path
) -> None:
    rows = _fixture_rows()
    manifest_path, batch_ids = _publish_manifest(tmp_path, rows)
    _insert_fixture(migrated_database, batch_ids, rows)

    first = build_temporal_split(
        manifest_path,
        repository_root=tmp_path,
        settings=migrated_database,
        lineage_reader=lambda _root: (COMMIT_SHA, True),
    )

    def unexpected_lineage_call(_root: Path) -> tuple[str, bool]:
        raise AssertionError("idempotent verification must use stored lineage")

    second = build_temporal_split(
        manifest_path,
        repository_root=tmp_path,
        settings=migrated_database,
        lineage_reader=unexpected_lineage_call,
    )

    assert first == second
    assert first["counts"] == {
        "input_eligible_count": 21,
        "included_record_count": 17,
        "excluded_record_count": 4,
        "output_record_count": 21,
    }
    assert first["exclusion_reason_counts"] == {
        "duplicate_same_label": 2,
        "duplicate_label_conflict": 2,
    }
    assert first["split_counts"] == {"train": 13, "validation": 2, "test": 2}
    assert all(first["checks"].values())
    assert first["privacy"]["contains_row_values"] is False
    assert (
        json.loads(
            (tmp_path / "data/manifests/cfpb/splits" / f"{RUN_ID}-split-1.0.0.json").read_text()
        )
        == first
    )

    with psycopg.connect(migrated_database.psycopg_conninfo()) as connection:
        leakage = connection.execute(
            """
            SELECT count(*) FROM (
                SELECT narrative_fingerprint_sha256
                FROM analytical.split_outcomes
                WHERE run_id = %s AND disposition = 'included'
                GROUP BY narrative_fingerprint_sha256
                HAVING count(DISTINCT split_assignment) > 1
            ) groups
            """,
            (RUN_ID,),
        ).fetchone()
        assert leakage == (0,)
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            connection.execute("UPDATE analytical.split_outcomes SET split_assignment = 'test'")


@pytest.mark.postgres
def test_split_rolls_back_run_when_outcome_insert_fails(
    migrated_database: DatabaseSettings, tmp_path: Path
) -> None:
    rows = _fixture_rows()
    manifest_path, batch_ids = _publish_manifest(tmp_path, rows)
    _insert_fixture(migrated_database, batch_ids, rows)
    with psycopg.connect(migrated_database.psycopg_conninfo()) as connection:
        connection.execute(
            """
            CREATE FUNCTION analytical.reject_test_split_outcome()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'test-only rejection';
            END;
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER reject_test_split_outcome
            BEFORE INSERT ON analytical.split_outcomes
            FOR EACH ROW EXECUTE FUNCTION analytical.reject_test_split_outcome()
            """
        )

    with pytest.raises(TemporalSplitError, match="split_database_failed"):
        build_temporal_split(
            manifest_path,
            repository_root=tmp_path,
            settings=migrated_database,
            lineage_reader=lambda _root: (COMMIT_SHA, True),
        )

    with psycopg.connect(migrated_database.psycopg_conninfo()) as connection:
        assert connection.execute("SELECT count(*) FROM analytical.split_runs").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM analytical.split_outcomes").fetchone() == (
            0,
        )
