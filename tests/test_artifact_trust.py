from pathlib import Path

import pytest

from complaint_triage.artifact_trust import TrustedArtifactPathError, resolve_trusted_artifact


def test_trusted_artifact_path_resolves_only_below_exact_prefix(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "cfpb" / "transformer" / "run" / "state.pt"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"aggregate fixture")

    assert (
        resolve_trusted_artifact(
            tmp_path,
            "artifacts/cfpb/transformer/run/state.pt",
            "artifacts/cfpb/transformer",
        )
        == artifact.resolve()
    )


@pytest.mark.parametrize(
    "relative_path",
    (
        "../artifacts/cfpb/transformer/run/state.pt",
        "artifacts/cfpb/transformer/../../outside.pt",
        "artifacts/cfpb/transformer-evil/run/state.pt",
        "/artifacts/cfpb/transformer/run/state.pt",
        r"artifacts\cfpb\transformer\run\state.pt",
    ),
)
def test_untrusted_artifact_paths_are_rejected(tmp_path: Path, relative_path: str) -> None:
    with pytest.raises(TrustedArtifactPathError):
        resolve_trusted_artifact(tmp_path, relative_path, "artifacts/cfpb/transformer")


def test_symbolic_link_artifact_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside.pt"
    outside.write_bytes(b"untrusted fixture")
    link = tmp_path / "artifacts" / "cfpb" / "transformer" / "run" / "state.pt"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic-link creation is unavailable on this platform")

    with pytest.raises(TrustedArtifactPathError, match="symbolic link"):
        resolve_trusted_artifact(
            tmp_path,
            "artifacts/cfpb/transformer/run/state.pt",
            "artifacts/cfpb/transformer",
        )
