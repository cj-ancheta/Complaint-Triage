import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[1]
COMPOSE_PATH = REPOSITORY_ROOT / "compose.yaml"
ENV_EXAMPLE_PATH = REPOSITORY_ROOT / ".env.example"


def test_compose_source_has_local_security_and_readiness_controls() -> None:
    compose_text = COMPOSE_PATH.read_text(encoding="utf-8")

    assert "postgres:18.4-alpine3.23" in compose_text
    assert "postgres:latest" not in compose_text
    assert "POSTGRES_HOST_AUTH_METHOD" not in compose_text
    assert "127.0.0.1:${POSTGRES_PORT:-55432}:5432" in compose_text
    assert "${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}" in compose_text
    assert "pg_isready" in compose_text
    assert "no-new-privileges:true" in compose_text
    assert "postgres_data:/var/lib/postgresql" in compose_text
    assert "PGDATA: /var/lib/postgresql/18/docker" in compose_text


def test_environment_example_uses_a_local_only_placeholder() -> None:
    env_text = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    assert "POSTGRES_DB=complaint_triage" in env_text
    assert "POSTGRES_USER=complaint_triage" in env_text
    assert "POSTGRES_PASSWORD=change-me-local-only" in env_text
    assert "POSTGRES_PORT=55432" in env_text
    assert ".env" in (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_docker_compose_renders_expected_service_contract() -> None:
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is not installed in this environment")

    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ENV_EXAMPLE_PATH),
            "-f",
            str(COMPOSE_PATH),
            "config",
            "--format",
            "json",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    )
    config = json.loads(completed.stdout)
    postgres = config["services"]["postgres"]

    assert postgres["image"] == "postgres:18.4-alpine3.23"
    assert postgres["environment"]["PGDATA"] == "/var/lib/postgresql/18/docker"
    assert postgres["ports"] == [
        {
            "mode": "ingress",
            "target": 5432,
            "published": "55432",
            "protocol": "tcp",
            "host_ip": "127.0.0.1",
        }
    ]
    assert postgres["healthcheck"]["test"][0] == "CMD-SHELL"
    assert "pg_isready" in postgres["healthcheck"]["test"][1]
    assert config["volumes"]["postgres_data"]["name"] == "complaint-triage-ml_postgres_data"
