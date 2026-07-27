"""Normalize and validate the browser-rendered publication PDF."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PDF_DATE_PATTERN = re.compile(rb"/(CreationDate|ModDate) \(D:\d{14}\+00'00'\)")
PAGE_PATTERN = re.compile(rb"/Type\s*/Page(?!s)")
TAG_PATTERN = re.compile(r"paper-v\d+\.\d+\.\d+")


def source_timestamp(tag: str) -> int:
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError(f"invalid paper tag: {tag}")
    result = subprocess.run(
        ["git", "show", "-s", "--format=%ct", f"refs/tags/{tag}^{{commit}}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def normalized_pdf_date(timestamp: int) -> bytes:
    instant = dt.datetime.fromtimestamp(timestamp, tz=dt.UTC)
    return instant.strftime("D:%Y%m%d%H%M%S+00'00'").encode("ascii")


def harden_pdf_bytes(content: bytes, *, timestamp: int) -> bytes:
    if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-1024:]:
        raise ValueError("file is not a complete PDF")
    if len(PAGE_PATTERN.findall(content)) < 1:
        raise ValueError("PDF has no page objects")

    replacement_date = normalized_pdf_date(timestamp)

    def replace(match: re.Match[bytes]) -> bytes:
        return b"/" + match.group(1) + b" (" + replacement_date + b")"

    hardened, replacements = PDF_DATE_PATTERN.subn(replace, content)
    if replacements != 2:
        raise ValueError(f"expected two PDF metadata dates, found {replacements}")
    if len(hardened) != len(content):
        raise AssertionError("PDF normalization changed byte offsets")
    return hardened


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    args = parser.parse_args(argv)
    pdf_path = args.pdf.resolve()
    hardened = harden_pdf_bytes(pdf_path.read_bytes(), timestamp=source_timestamp(args.tag))
    pdf_path.write_bytes(hardened)
    print(pdf_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
