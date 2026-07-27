import datetime as dt
import importlib.util

import pytest

from complaint_triage.real_extraction import PROJECT_ROOT


def _load_script(name: str):
    path = PROJECT_ROOT / "paper" / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PDF = _load_script("harden_pdf.py")
SUBMISSION = _load_script("finalize_submission.py")


def _pdf_fixture(date: bytes = b"D:20260727030338+00'00'") -> bytes:
    pages = b"\n".join(b"<</Type /Page>>" for _ in range(25))
    return (
        b"%PDF-1.7\n"
        + b"<</CreationDate ("
        + date
        + b") /ModDate ("
        + date
        + b")>>\n"
        + pages
        + b"\n%%EOF\n"
    )


def test_pdf_metadata_is_normalized_without_changing_offsets() -> None:
    timestamp = 1_700_000_000
    original = _pdf_fixture()

    hardened = PDF.harden_pdf_bytes(original, timestamp=timestamp)
    expected = dt.datetime.fromtimestamp(timestamp, tz=dt.UTC).strftime("D:%Y%m%d%H%M%S+00'00'")

    assert len(hardened) == len(original)
    assert hardened.count(expected.encode("ascii")) == 2
    assert PDF.harden_pdf_bytes(hardened, timestamp=timestamp) == hardened
    assert SUBMISSION.validate_pdf(hardened, source_timestamp=timestamp) == 25


@pytest.mark.parametrize(
    "content",
    (
        b"not a PDF",
        b"%PDF-1.7\n<</CreationDate (D:20260727030338+00'00')>>\n%%EOF\n",
        _pdf_fixture(date=b"D:20260727030338-05'00'"),
    ),
)
def test_pdf_hardening_rejects_incomplete_or_unexpected_input(content: bytes) -> None:
    with pytest.raises(ValueError):
        PDF.harden_pdf_bytes(content, timestamp=1_700_000_000)


def test_final_identity_requires_reserved_doi_in_every_source() -> None:
    doi = "10.5281/zenodo.1234567"
    SUBMISSION.validate_identity_texts(
        citation=f"version: 1.0.2\ndoi: {doi}\npreferred-citation:\n  doi: {doi}\n",
        manuscript=f"Version 1.0.2\nDOI: https://doi.org/{doi}\n",
        deposit=f"| Version | 1.0.2 |\n| DOI | {doi} |\n",
        version="1.0.2",
        doi=doi,
    )

    with pytest.raises(ValueError, match="manuscript does not contain reserved DOI"):
        SUBMISSION.validate_identity_texts(
            citation=f"version: 1.0.2\ndoi: {doi}\npreferred-citation:\n  doi: {doi}\n",
            manuscript="Version 1.0.2\n",
            deposit=f"| Version | 1.0.2 |\n| DOI | {doi} |\n",
            version="1.0.2",
            doi=doi,
        )


def test_final_html_is_offline_and_preserves_claim_boundaries() -> None:
    doi = "10.5281/zenodo.1234567"
    figures = "".join('<img src="data:image/svg+xml;base64,AAAA">' for _ in range(7))
    html = (
        f"<!doctype html><html><body>{figures}{doi} validation-only "
        "manual review only; not a conducted trial</body></html>"
    ).encode()
    SUBMISSION.validate_html(html, doi=doi)

    with pytest.raises(ValueError, match="remote image"):
        SUBMISSION.validate_html(
            html.replace(
                b"data:image/svg+xml;base64,AAAA",
                b"https://example.com/figure.svg",
                1,
            ),
            doi=doi,
        )


def test_final_package_allowlist_is_exact_and_versioned() -> None:
    names = SUBMISSION.expected_names("1.0.2")

    assert len(names) == 11
    assert "when-aggregate-accuracy-is-not-enough-v1.0.2.pdf" in names
    assert "submission-manifest-v1.0.2.json" in names
    assert all("v1.0.1" not in name for name in names)


@pytest.mark.parametrize(
    "doi",
    ("", "reserved-doi", "10.5281/zenodo.<reserved-number>", "https://example.com/123"),
)
def test_doi_validation_rejects_missing_or_placeholder_values(doi: str) -> None:
    with pytest.raises(ValueError):
        SUBMISSION.validate_doi(doi)
