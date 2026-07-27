import importlib.util
from pathlib import Path

from complaint_triage.real_extraction import PROJECT_ROOT

SCRIPT_PATH = PROJECT_ROOT / "paper" / "scripts" / "render_preprint.py"
SPEC = importlib.util.spec_from_file_location("render_preprint", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_print_document_embeds_local_svg_and_records_release_boundary(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "figure.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><title>Safe figure</title></svg>',
        encoding="utf-8",
    )
    fragment = '<h1>Paper</h1><p><img src="generated/figure.svg" alt="Figure"></p>'

    document = MODULE.build_document(
        fragment,
        source_dir=tmp_path,
        title="Paper title",
        tag="paper-v1.0.0",
        commit="4f6d2fd3fb652f67f41ab6cb201c5cc08d6e257b",
    )

    assert "data:image/svg+xml;base64," in document
    assert 'src="generated/figure.svg"' not in document
    assert "paper-v1.0.0" in document
    assert "validation-only" in document
    assert "not a conducted trial" in document
    assert "<script" not in document


def test_print_document_rejects_svg_path_outside_paper_directory(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.svg"
    outside.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8")
    fragment = '<img src="../outside.svg" alt="Figure">'

    try:
        MODULE.build_document(
            fragment,
            source_dir=tmp_path,
            title="Paper title",
            tag="paper-v1.0.0",
            commit="4f6d2fd3fb652f67f41ab6cb201c5cc08d6e257b",
        )
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("renderer accepted an SVG outside the source directory")


def test_print_document_can_load_figures_from_an_immutable_source(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    fragment = '<img src="generated/figure.svg" alt="Figure">'
    requested: list[Path] = []

    def load_from_tag(path: Path) -> bytes:
        requested.append(path)
        return b'<svg xmlns="http://www.w3.org/2000/svg"><title>Tagged</title></svg>'

    document = MODULE.build_document(
        fragment,
        source_dir=tmp_path,
        title="Paper title",
        tag="paper-v1.0.0",
        commit="4f6d2fd3fb652f67f41ab6cb201c5cc08d6e257b",
        image_loader=load_from_tag,
    )

    assert requested == [generated / "figure.svg"]
    assert "data:image/svg+xml;base64," in document


def test_tag_lookup_rejects_option_or_traversal_injection() -> None:
    for tag in ("--help", "paper-v1.0.0..malicious", "paper:v1"):
        try:
            MODULE._tag_commit(tag)
        except ValueError:
            pass
        else:
            raise AssertionError(f"renderer accepted unsafe tag: {tag}")
