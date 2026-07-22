import json
import os
import shutil
import uuid
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql

from complaint_triage.db import DatabaseSettings, DatabaseSettingsError
from complaint_triage.raw_ingestion import RawIngestionError, ingest_raw_batch

REPOSITORY_ROOT = Path(__file__).parents[1]
MANIFEST_FIXTURE = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "cfpb" / "raw_batch_manifest_synthetic.json"
)
ARTIFACT_FIXTURE = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "cfpb" / "search_response_synthetic.json"
)


def _server_settings() -> DatabaseSettings:
    try:
        return DatabaseSettings.from_environment(env_file=REPOSITORY_ROOT / ".env")
    except DatabaseSettingsError as error:
        pytest.skip(f"PostgreSQL settings are unavailable: {error}")


@pytest.fixture
def migrated_database(monkeypatch: pytest.MonkeyPatch) -> DatabaseSettings:
    if os.environ.get("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests")

    server = _server_settings()
    database_name = f"ct_test_{uuid.uuid4().hex}"
    try:
        with psycopg.connect(server.psycopg_conninfo(), autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    except psycopg.Error as error:
        pytest.skip(
            f"Disposable PostgreSQL database could not be created: {error.__class__.__name__}"
        )

    settings = DatabaseSettings(
        database=database_name,
        user=server.user,
        password=server.password,
        host=server.host,
        port=server.port,
    )
    monkeypatch.setenv("POSTGRES_DB", database_name)
    monkeypatch.setenv("POSTGRES_USER", settings.user)
    monkeypatch.setenv("POSTGRES_PASSWORD", settings.password)
    monkeypatch.setenv("POSTGRES_HOST", settings.host)
    monkeypatch.setenv("POSTGRES_PORT", str(settings.port))
    command.upgrade(Config(REPOSITORY_ROOT / "alembic.ini"), "head")

    try:
        yield settings
    finally:
        with psycopg.connect(server.psycopg_conninfo(), autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
            )


def _stage_batch(tmp_path: Path) -> Path:
    manifest = json.loads(MANIFEST_FIXTURE.read_text(encoding="utf-8"))
    manifest_path = tmp_path / "data" / "manifests" / "cfpb" / "batch.json"
    artifact_path = tmp_path / Path(*Path(manifest["artifact"]["relative_path"]).parts)
    manifest_path.parent.mkdir(parents=True)
    artifact_path.parent.mkdir(parents=True)
    shutil.copyfile(MANIFEST_FIXTURE, manifest_path)
    shutil.copyfile(ARTIFACT_FIXTURE, artifact_path)
    return manifest_path


@pytest.mark.postgres
def test_ingestion_is_atomic_idempotent_reconciled_and_append_only(
    tmp_path: Path, migrated_database: DatabaseSettings
) -> None:
    manifest_path = _stage_batch(tmp_path)
    conninfo = migrated_database.psycopg_conninfo()

    with psycopg.connect(conninfo) as connection:
        connection.execute(
            """
            CREATE FUNCTION raw.reject_second_synthetic_record()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NEW.complaint_id = 'SYN-0002' THEN
                    RAISE EXCEPTION 'test-only rejection';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        connection.execute(
            """
            CREATE TRIGGER reject_second_synthetic_record
            BEFORE INSERT ON raw.complaints
            FOR EACH ROW EXECUTE FUNCTION raw.reject_second_synthetic_record()
            """
        )

    with pytest.raises(RawIngestionError) as raised:
        ingest_raw_batch(manifest_path, repository_root=tmp_path, settings=migrated_database)
    assert raised.value.code == "database_write_failed"

    with psycopg.connect(conninfo) as connection:
        assert connection.execute("SELECT count(*) FROM raw.ingestion_batches").fetchone() == (0,)
        assert connection.execute("SELECT count(*) FROM raw.complaints").fetchone() == (0,)
        connection.execute("DROP TRIGGER reject_second_synthetic_record ON raw.complaints")
        connection.execute("DROP FUNCTION raw.reject_second_synthetic_record()")

    first = ingest_raw_batch(manifest_path, repository_root=tmp_path, settings=migrated_database)
    second = ingest_raw_batch(manifest_path, repository_root=tmp_path, settings=migrated_database)

    assert first["status"] == "inserted"
    assert first["inserted_record_count"] == 3
    assert second["status"] == "already_ingested"
    assert second["inserted_record_count"] == 0

    with psycopg.connect(conninfo) as connection:
        batch_counts = connection.execute(
            """
            SELECT returned_record_count, inserted_record_count
            FROM raw.ingestion_batches
            """
        ).fetchone()
        complaint_count = connection.execute("SELECT count(*) FROM raw.complaints").fetchone()
        assert batch_counts == (3, 3)
        assert complaint_count == (3,)

        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            connection.execute(
                "UPDATE raw.complaints SET complaint_id = 'changed' WHERE source_row_ordinal = 0"
            )
        connection.rollback()
        with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            connection.execute("DELETE FROM raw.ingestion_batches")
