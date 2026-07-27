"""Assemble and verify the exact, DOI-bearing final preprint deposit."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BUILD_ROOT = PROJECT_ROOT / "paper" / "release-build"
DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+")
PAGE_PATTERN = re.compile(rb"/Type\s*/Page(?!s)")

SOURCE_ASSETS = {
    "CITATION-v{version}.cff": "CITATION.cff",
    "manuscript-v{version}.md": "paper/manuscript.md",
    "impact-statement-v{version}.md": "paper/impact_statement.md",
    "prospective-causal-protocol-v{version}.md": "paper/prospective_causal_protocol.md",
    "paper-source-manifest-v{version}.json": "paper/generated/source_manifest.json",
    "submission-summary-v{version}.md": "paper/submission/submission_summary.md",
    "zenodo-deposit-metadata-v{version}.md": "paper/submission/deposit_metadata.md",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tag_commit(tag: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def tagged_file(tag: str, source: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"refs/tags/{tag}:{source}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout


def expected_names(version: str) -> set[str]:
    return {
        f"when-aggregate-accuracy-is-not-enough-v{version}.pdf",
        f"when-aggregate-accuracy-is-not-enough-v{version}.html",
        f"release-artifact-manifest-v{version}.json",
        f"submission-manifest-v{version}.json",
        *(template.format(version=version) for template in SOURCE_ASSETS),
    }


def validate_doi(doi: str) -> str:
    normalized = doi.removeprefix("https://doi.org/").strip()
    if not DOI_PATTERN.fullmatch(normalized):
        raise ValueError("DOI must be a real reserved DOI, for example 10.5281/zenodo.1234567")
    return normalized


def validate_identity_texts(
    *, citation: str, manuscript: str, deposit: str, version: str, doi: str
) -> None:
    doi_url = f"https://doi.org/{doi}"
    requirements = {
        "CITATION.cff": (citation, f"version: {version}", f"doi: {doi}"),
        "manuscript": (manuscript, f"Version {version}", doi_url),
        "deposit metadata": (deposit, f"| Version | {version} |", doi),
    }
    for label, (text, version_marker, doi_marker) in requirements.items():
        if version_marker not in text:
            raise ValueError(f"{label} does not identify version {version}")
        if doi_marker not in text:
            raise ValueError(f"{label} does not contain reserved DOI {doi}")
    if citation.count(f"doi: {doi}") < 2:
        raise ValueError("CITATION.cff must attach the DOI to the work and preferred citation")


def validate_html(content: bytes, *, doi: str) -> None:
    text = content.decode("utf-8")
    lowered = text.lower()
    if re.search(r'<img[^>]+src="https?://', lowered):
        raise ValueError("HTML contains a remote image dependency")
    if lowered.count("data:image/svg+xml;base64,") != 7:
        raise ValueError("HTML must embed exactly seven SVG figures")
    if "<script" in lowered:
        raise ValueError("HTML contains an executable script")
    for marker in (
        doi,
        "validation-only",
        "manual review only",
        "not a conducted trial",
    ):
        if marker not in lowered:
            raise ValueError(f"HTML is missing required boundary: {marker}")


def validate_pdf(content: bytes, *, source_timestamp: int) -> int:
    if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-1024:]:
        raise ValueError("primary file is not a complete PDF")
    pages = len(PAGE_PATTERN.findall(content))
    if not 15 <= pages <= 40:
        raise ValueError(f"unexpected PDF page count: {pages}")
    expected_date = dt.datetime.fromtimestamp(source_timestamp, tz=dt.UTC).strftime(
        "D:%Y%m%d%H%M%S+00'00'"
    )
    if content.count(expected_date.encode("ascii")) != 2:
        raise ValueError("PDF metadata was not normalized to the source commit")
    return pages


def tag_timestamp(tag: str) -> int:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%ct", f"refs/tags/{tag}^{{commit}}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip())


def artifact_entries(package_root: Path, *, manifest_name: str) -> list[dict[str, object]]:
    entries = []
    for path in sorted(package_root.iterdir(), key=lambda item: item.name.lower()):
        if path.name == manifest_name:
            continue
        entries.append({"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return entries


def build_manifest(
    package_root: Path, *, version: str, tag: str, commit: str, doi: str, pages: int
) -> dict[str, object]:
    manifest_name = f"submission-manifest-v{version}.json"
    return {
        "schema_version": "1.0.0",
        "package_status": "final_submission_candidate",
        "paper_version": version,
        "reserved_doi": doi,
        "doi_url": f"https://doi.org/{doi}",
        "source_tag": tag,
        "source_commit": commit,
        "primary_file": f"when-aggregate-accuracy-is-not-enough-v{version}.pdf",
        "pdf_pages": pages,
        "evidence_boundary": "validation_only_causal_design_not_conducted",
        "operational_decision": "manual_review_only",
        "rights": "All rights reserved",
        "files": artifact_entries(package_root, manifest_name=manifest_name),
    }


def validate_artifact_manifest(
    package_root: Path, *, version: str, tag: str, commit: str, doi: str
) -> None:
    path = package_root / f"release-artifact-manifest-v{version}.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    expected = {
        "paper_version": version,
        "source_tag": tag,
        "source_commit": commit,
        "reserved_doi": doi,
        "evidence_boundary": "validation_only_causal_design_not_conducted",
        "pdf_metadata_time": "normalized_to_source_commit",
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise ValueError(f"artifact manifest mismatch for {key}")
    entries = payload.get("files", [])
    expected_assets = {
        f"when-aggregate-accuracy-is-not-enough-v{version}.html",
        f"when-aggregate-accuracy-is-not-enough-v{version}.pdf",
    }
    if {entry.get("name") for entry in entries} != expected_assets:
        raise ValueError("artifact manifest must contain exactly the PDF and HTML")
    for entry in entries:
        asset = package_root / entry["name"]
        if asset.stat().st_size != entry["bytes"] or sha256(asset) != entry["sha256"]:
            raise ValueError(f"artifact hash mismatch: {asset.name}")


def validate_tag_sources(*, version: str, tag: str, doi: str) -> tuple[str, str, dict[str, bytes]]:
    if not VERSION_PATTERN.fullmatch(version) or tag != f"paper-v{version}":
        raise ValueError("final tag must exactly match paper-v<version>")
    doi = validate_doi(doi)
    commit = tag_commit(tag)
    source_content = {
        template.format(version=version): tagged_file(tag, source)
        for template, source in SOURCE_ASSETS.items()
    }
    citation = source_content[f"CITATION-v{version}.cff"].decode("utf-8")
    manuscript = source_content[f"manuscript-v{version}.md"].decode("utf-8")
    deposit = source_content[f"zenodo-deposit-metadata-v{version}.md"].decode("utf-8")
    validate_identity_texts(
        citation=citation,
        manuscript=manuscript,
        deposit=deposit,
        version=version,
        doi=doi,
    )
    return doi, commit, source_content


def assemble(*, version: str, tag: str, doi: str, check: bool) -> Path:
    doi, commit, source_content = validate_tag_sources(version=version, tag=tag, doi=doi)
    package_root = BUILD_ROOT / f"v{version}"
    package_root.mkdir(parents=True, exist_ok=True)

    if not check:
        for name, content in source_content.items():
            (package_root / name).write_bytes(content)

    for name, content in source_content.items():
        if (package_root / name).read_bytes() != content:
            raise ValueError(f"packaged source differs from immutable tag: {name}")

    actual_names = {path.name for path in package_root.iterdir()}
    allowed_names = expected_names(version)
    manifest_name = f"submission-manifest-v{version}.json"
    required_now = allowed_names if check else allowed_names - {manifest_name}
    missing = required_now - actual_names
    unexpected = actual_names - allowed_names
    if missing or unexpected:
        raise ValueError(
            "package allowlist mismatch; "
            f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
        )

    html_path = package_root / f"when-aggregate-accuracy-is-not-enough-v{version}.html"
    pdf_path = package_root / f"when-aggregate-accuracy-is-not-enough-v{version}.pdf"
    validate_html(html_path.read_bytes(), doi=doi.lower())
    pages = validate_pdf(pdf_path.read_bytes(), source_timestamp=tag_timestamp(tag))
    validate_artifact_manifest(
        package_root,
        version=version,
        tag=tag,
        commit=commit,
        doi=doi,
    )

    manifest_path = package_root / manifest_name
    expected_manifest = build_manifest(
        package_root,
        version=version,
        tag=tag,
        commit=commit,
        doi=doi,
        pages=pages,
    )
    rendered_manifest = json.dumps(expected_manifest, indent=2, ensure_ascii=False) + "\n"
    if check:
        if manifest_path.read_text(encoding="utf-8") != rendered_manifest:
            raise ValueError("submission manifest is stale or does not match package bytes")
    else:
        manifest_path.write_text(rendered_manifest, encoding="utf-8", newline="\n")
    return package_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--doi", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    args = parser.parse_args(argv)
    if args.preflight:
        doi, commit, _ = validate_tag_sources(
            version=args.version,
            tag=args.tag,
            doi=args.doi,
        )
        print(f"preflight passed: {args.tag} {commit} {doi}")
        return 0
    package_root = assemble(
        version=args.version,
        tag=args.tag,
        doi=args.doi,
        check=args.check,
    )
    print(package_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
