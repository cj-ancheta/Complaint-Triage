import json

from complaint_triage import cli
from complaint_triage.cfpb_profile import ProfileError


def test_profile_command_prints_safe_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "fetch_cfpb_profile",
        lambda: {
            "status": "ok",
            "result": {"returned_hit_count": 3},
            "privacy": {"source_values_logged": False},
        },
    )

    exit_code = cli.main(["profile-cfpb"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["result"]["returned_hit_count"] == 3
    assert output["privacy"]["source_values_logged"] is False


def test_profile_command_returns_controlled_error_without_exception_text(
    monkeypatch, capsys
) -> None:
    def fail() -> None:
        raise ProfileError(
            "http_error",
            requested_at_utc="2026-07-21T05:00:00+00:00",
            http_status=403,
        )

    monkeypatch.setattr(cli, "fetch_cfpb_profile", fail)

    exit_code = cli.main(["profile-cfpb"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["error"]["code"] == "http_error"
    assert output["error"]["http_status"] == 403
    assert output["privacy"]["response_body_logged"] is False
