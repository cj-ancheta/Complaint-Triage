"""Fail-closed path boundary for ignored, trusted-local model artifacts."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class TrustedArtifactPathError(ValueError):
    """An artifact reference escapes or weakens its declared local boundary."""


def resolve_trusted_artifact(root: Path, relative_path: object, trusted_prefix: str) -> Path:
    """Resolve a canonical relative artifact path and reject links or traversal."""
    if not isinstance(relative_path, str) or not relative_path:
        raise TrustedArtifactPathError("artifact path must be a non-empty string")

    relative = PurePosixPath(relative_path)
    prefix = PurePosixPath(trusted_prefix)
    if (
        relative.is_absolute()
        or relative.as_posix() != relative_path
        or relative.parts[: len(prefix.parts)] != prefix.parts
        or len(relative.parts) <= len(prefix.parts)
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise TrustedArtifactPathError("artifact path is outside the trusted prefix")

    project_root = root.resolve()
    candidate = project_root.joinpath(*relative.parts)
    current = project_root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise TrustedArtifactPathError("artifact path contains a symbolic link")

    trusted_root = project_root.joinpath(*prefix.parts)
    resolved = candidate.resolve()
    if not resolved.is_relative_to(trusted_root):
        raise TrustedArtifactPathError("artifact path resolves outside the trusted prefix")
    return resolved
