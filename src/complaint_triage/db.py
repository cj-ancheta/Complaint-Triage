"""Database configuration shared by migrations and ingestion commands."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from psycopg.conninfo import make_conninfo
from sqlalchemy import URL


class DatabaseSettingsError(ValueError):
    """Raised when database configuration is missing or malformed."""


@dataclass(frozen=True)
class DatabaseSettings:
    database: str
    user: str
    password: str
    host: str = "127.0.0.1"
    port: int = 55432

    @classmethod
    def from_environment(
        cls,
        *,
        env_file: Path | None = Path(".env"),
        environ: Mapping[str, str] | None = None,
    ) -> DatabaseSettings:
        values = _read_env_file(env_file) if env_file is not None else {}
        values.update(dict(os.environ if environ is None else environ))

        required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
        missing = [name for name in required if not values.get(name)]
        if missing:
            raise DatabaseSettingsError(
                f"Missing required database settings: {', '.join(sorted(missing))}"
            )

        raw_port = values.get("POSTGRES_PORT", "55432")
        try:
            port = int(raw_port)
        except ValueError as error:
            raise DatabaseSettingsError("POSTGRES_PORT must be an integer") from error
        if not 1 <= port <= 65535:
            raise DatabaseSettingsError("POSTGRES_PORT must be between 1 and 65535")

        return cls(
            database=values["POSTGRES_DB"],
            user=values["POSTGRES_USER"],
            password=values["POSTGRES_PASSWORD"],
            host=values.get("POSTGRES_HOST", "127.0.0.1"),
            port=port,
        )

    def psycopg_conninfo(self, *, database: str | None = None) -> str:
        return make_conninfo(
            dbname=database or self.database,
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
        )

    def sqlalchemy_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )

    def __repr__(self) -> str:
        return (
            "DatabaseSettings("
            f"database={self.database!r}, user={self.user!r}, password=<redacted>, "
            f"host={self.host!r}, port={self.port!r})"
        )


def _read_env_file(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise DatabaseSettingsError(f"Invalid environment entry on line {line_number}")
        name, value = line.split("=", 1)
        name = name.strip()
        if not name:
            raise DatabaseSettingsError(f"Invalid environment key on line {line_number}")
        values[name] = value.strip()
    return values
