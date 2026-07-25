"""Privacy-bounded software-supply-chain evidence helpers."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
from typing import Any

TORCH_CPU_VERSION = "2.13.0+cpu"
TORCH_CPU_SHA256 = "4ca4a9394b0c771238a4f73590fdbbc4debad85ed0fa63d026ae1b085da7d6e2"


def complete_transformer_sbom(payload: dict[str, Any], torch_version: str) -> dict[str, Any]:
    """Add the hash-locked non-PyPI Torch wheel to a CycloneDX payload."""
    if payload.get("bomFormat") != "CycloneDX" or not isinstance(payload.get("components"), list):
        raise ValueError("expected a CycloneDX document with a component list")
    if torch_version != TORCH_CPU_VERSION:
        raise ValueError("installed CPU Torch identity does not match the reviewed lock")

    components = payload["components"]
    if not any(component.get("name") == "torch" for component in components):
        components.append(
            {
                "type": "library",
                "name": "torch",
                "version": TORCH_CPU_VERSION,
                "purl": "pkg:pypi/torch@2.13.0%2Bcpu",
                "hashes": [{"alg": "SHA-256", "content": TORCH_CPU_SHA256}],
                "properties": [
                    {
                        "name": "complaint-triage:audit-boundary",
                        "value": "non-PyPI hash-locked CPU wheel; absent from OSV lookup",
                    }
                ],
            }
        )
    return payload


def complete_transformer_sbom_file(path: Path) -> None:
    """Complete and privacy-check a generated transformer SBOM in place."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    completed = complete_transformer_sbom(payload, importlib.metadata.version("torch"))
    rendered = json.dumps(completed, indent=2, sort_keys=True) + "\n"
    if "/home/runner" in rendered or "POSTGRES_PASSWORD" in rendered:
        raise ValueError("SBOM contains a prohibited path or environment value")
    path.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sbom", type=Path)
    args = parser.parse_args()
    complete_transformer_sbom_file(args.sbom)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
