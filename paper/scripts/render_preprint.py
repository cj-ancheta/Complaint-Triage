"""Render the paper through GitHub's GFM API into a self-contained HTML file."""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import re
import subprocess
import urllib.request
from collections.abc import Callable
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = PROJECT_ROOT / "paper" / "manuscript.md"
DEFAULT_OUTPUT = PROJECT_ROOT / "paper" / "release-build" / "preprint.html"
REPOSITORY = "cj-ancheta/Complaint-Triage"
SVG_IMAGE_PATTERN = re.compile(r'(<img\b[^>]*\bsrc=")([^"]+\.svg)("[^>]*>)', re.IGNORECASE)
TAG_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")

STYLE = """
:root { color-scheme: light; }
@page { size: A4; margin: 18mm 17mm 20mm; }
* { box-sizing: border-box; }
html { background: #eef1f5; }
body {
  max-width: 210mm; margin: 24px auto; padding: 20mm 18mm;
  background: #fff; color: #172033; font: 10.5pt/1.55 Georgia, serif;
}
h1, h2, h3 { color: #102a43; font-family: Arial, sans-serif; line-height: 1.2; }
h1 { margin: 0 0 0.3em; font-size: 25pt; }
h2 { margin-top: 1.7em; font-size: 17pt; break-after: avoid; }
h3 { margin-top: 1.35em; font-size: 13pt; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
a { color: #075985; text-decoration: none; }
blockquote {
  margin: 1.2em 0; padding: 0.7em 1em;
  border-left: 4px solid #d55e00; background: #fff7ed;
}
table {
  width: 100%; margin: 1.2em 0; border-collapse: collapse;
  font: 8.8pt/1.35 Arial, sans-serif; break-inside: avoid;
}
th, td { padding: 6px 7px; border: 1px solid #cbd5e1; vertical-align: top; }
th { background: #eaf2f8; color: #102a43; }
img { display: block; max-width: 100%; height: auto; margin: 1.2em auto; break-inside: avoid; }
code { padding: 0.08em 0.25em; background: #f1f5f9; font: 0.9em Consolas, monospace; }
pre { overflow-wrap: anywhere; white-space: pre-wrap; }
.release-note {
  margin-top: 2.5em; padding-top: 1em; border-top: 1px solid #cbd5e1;
  color: #52606d; font: 8.5pt/1.4 Arial, sans-serif;
}
@media print {
  html, body { background: #fff; }
  body { max-width: none; margin: 0; padding: 0; }
  a { color: inherit; }
  h2 { break-before: auto; }
}
"""


def render_gfm(markdown: str, *, repository: str = REPOSITORY) -> str:
    payload = json.dumps({"text": markdown, "mode": "gfm", "context": repository}).encode()
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "complaint-triage-preprint-renderer",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        "https://api.github.com/markdown",
        data=payload,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def _embed_svg_images(
    fragment: str,
    *,
    source_dir: Path,
    image_loader: Callable[[Path], bytes] | None = None,
) -> str:
    def replace(match: re.Match[str]) -> str:
        relative = match.group(2)
        if relative.startswith(("http://", "https://", "data:")):
            return match.group(0)
        path = (source_dir / relative).resolve()
        if not path.is_relative_to(source_dir.resolve()):
            raise FileNotFoundError(f"cannot embed paper figure: {relative}")
        if image_loader is None:
            if not path.is_file():
                raise FileNotFoundError(f"cannot embed paper figure: {relative}")
            content = path.read_bytes()
        else:
            content = image_loader(path)
        encoded = base64.b64encode(content).decode("ascii")
        return f"{match.group(1)}data:image/svg+xml;base64,{encoded}{match.group(3)}"

    return SVG_IMAGE_PATTERN.sub(replace, fragment)


def build_document(
    fragment: str,
    *,
    source_dir: Path,
    title: str,
    tag: str,
    commit: str,
    repository: str = REPOSITORY,
    image_loader: Callable[[Path], bytes] | None = None,
) -> str:
    embedded = _embed_svg_images(
        fragment,
        source_dir=source_dir,
        image_loader=image_loader,
    )
    base_url = f"https://github.com/{repository}/blob/{tag}/paper/"
    release_url = f"https://github.com/{repository}/releases/tag/{tag}"
    return "\n".join(
        (
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{html.escape(title)}</title>",
            f'<base href="{html.escape(base_url)}">',
            f"<style>{STYLE}</style>",
            "</head>",
            "<body>",
            '<main class="markdown-body">',
            embedded,
            "</main>",
            '<footer class="release-note">',
            f'Public preprint <a href="{release_url}">{html.escape(tag)}</a>; '
            f"source commit <code>{html.escape(commit)}</code>. ",
            "Empirical results are validation-only. The causal evaluation is a design "
            "blueprint, not a conducted trial.",
            "</footer>",
            "</body>",
            "</html>",
            "",
        )
    )


def _tag_commit(tag: str) -> str:
    if not TAG_PATTERN.fullmatch(tag) or ".." in tag:
        raise ValueError(f"invalid tag name: {tag}")
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    commit = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError(f"tag did not resolve to a commit: {tag}")
    return commit


def _tag_file(tag: str, path: Path) -> bytes:
    if not TAG_PATTERN.fullmatch(tag) or ".." in tag:
        raise ValueError(f"invalid tag name: {tag}")
    try:
        relative = path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError as error:
        raise ValueError(f"tagged source must be inside the repository: {path}") from error
    result = subprocess.run(
        ["git", "show", f"refs/tags/{tag}:{relative}"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tag", default="paper-v1.0.0")
    parser.add_argument(
        "--title",
        default=(
            "When Aggregate Accuracy Is Not Enough: Decision Impact, Validation "
            "Governance, and a Causal Evaluation Blueprint for Financial Complaint Triage"
        ),
    )
    args = parser.parse_args(argv)
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_file():
        parser.error(f"source does not exist: {source}")
    tagged_markdown = _tag_file(args.tag, source).decode("utf-8")
    fragment = render_gfm(tagged_markdown)
    document = build_document(
        fragment,
        source_dir=source.parent,
        title=args.title,
        tag=args.tag,
        commit=_tag_commit(args.tag),
        image_loader=lambda path: _tag_file(args.tag, path),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8", newline="\n")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
