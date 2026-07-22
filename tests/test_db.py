from pathlib import Path

import pytest

from complaint_triage.db import DatabaseSettings, DatabaseSettingsError


def test_environment_overrides_env_file_and_password_is_redacted(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_DB=file_db\n"
        "POSTGRES_USER=file_user\n"
        "POSTGRES_PASSWORD=file-secret\n"
        "POSTGRES_PORT=55432\n",
        encoding="utf-8",
    )

    settings = DatabaseSettings.from_environment(
        env_file=env_file,
        environ={
            "POSTGRES_DB": "environment_db",
            "POSTGRES_PASSWORD": "environment-secret",
            "POSTGRES_USER": "environment_user",
        },
    )

    assert settings.database == "environment_db"
    assert settings.host == "127.0.0.1"
    assert settings.port == 55432
    assert "environment-secret" not in repr(settings)
    assert "environment-secret" not in str(settings.sqlalchemy_url())
    assert "dbname=environment_db" in settings.psycopg_conninfo()


@pytest.mark.parametrize("port", ["not-a-number", "0", "65536"])
def test_invalid_database_port_is_rejected(port: str) -> None:
    with pytest.raises(DatabaseSettingsError):
        DatabaseSettings.from_environment(
            env_file=None,
            environ={
                "POSTGRES_DB": "database",
                "POSTGRES_USER": "user",
                "POSTGRES_PASSWORD": "secret",
                "POSTGRES_PORT": port,
            },
        )


def test_missing_required_database_setting_is_rejected() -> None:
    with pytest.raises(DatabaseSettingsError, match="POSTGRES_PASSWORD"):
        DatabaseSettings.from_environment(
            env_file=None,
            environ={"POSTGRES_DB": "database", "POSTGRES_USER": "user"},
        )
