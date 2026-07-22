import os
import uuid
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql

from complaint_triage.db import DatabaseSettings, DatabaseSettingsError

REPOSITORY_ROOT = Path(__file__).parents[1]


def _server_settings() -> DatabaseSettings:
    try:
        return DatabaseSettings.from_environment(env_file=REPOSITORY_ROOT / ".env")
    except DatabaseSettingsError as error:
        pytest.skip(f"PostgreSQL settings are unavailable: {error}")


@pytest.fixture
def migrated_database(monkeypatch: pytest.MonkeyPatch) -> DatabaseSettings:
    """Create an exact disposable database and migrate it to the current head."""

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
