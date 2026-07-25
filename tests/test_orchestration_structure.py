import argparse
import ast
from pathlib import Path

from complaint_triage.cli import SIMPLE_COMMANDS, SPECIAL_COMMANDS
from complaint_triage.cli_parser import build_parser
from complaint_triage.real_extraction import PROJECT_ROOT


def _function_spans(path: Path) -> dict[str, int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node.end_lineno - node.lineno + 1
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.end_lineno is not None
    }


def test_every_public_command_has_exactly_one_handler() -> None:
    parser = build_parser()
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    parsed_commands = set(subparsers.choices)
    simple_commands = set(SIMPLE_COMMANDS)
    special_commands = set(SPECIAL_COMMANDS)

    assert simple_commands.isdisjoint(special_commands)
    assert parsed_commands == simple_commands | special_commands
    assert len(parsed_commands) == 20


def test_orchestration_size_ratchets_preserve_bounded_phases() -> None:
    cli_path = PROJECT_ROOT / "src/complaint_triage/cli.py"
    parser_path = PROJECT_ROOT / "src/complaint_triage/cli_parser.py"
    fit_path = PROJECT_ROOT / "src/complaint_triage/transformer_fit.py"
    calibration_path = PROJECT_ROOT / "src/complaint_triage/transformer_calibration.py"

    cli_spans = _function_spans(cli_path)
    parser_spans = _function_spans(parser_path)
    fit_spans = _function_spans(fit_path)
    calibration_spans = _function_spans(calibration_path)

    assert len(cli_path.read_text(encoding="utf-8").splitlines()) < 400
    assert cli_spans["main"] <= 3
    assert cli_spans["dispatch"] <= 12
    assert max(parser_spans.values()) <= 50
    assert fit_spans["train_transformer"] <= 60
    assert fit_spans["_prepare_fit"] <= 70
    assert fit_spans["_run_training_epochs"] <= 125
    assert calibration_spans["calibrate_transformer"] <= 140


def test_calibration_report_builder_has_no_io_or_environment_access() -> None:
    source = (PROJECT_ROOT / "src/complaint_triage/transformer_calibration.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    builder = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_build_calibration_report"
    )
    builder_source = ast.get_source_segment(source, builder)

    assert builder_source is not None
    for prohibited in ("read_text(", "write_text(", "_atomic_json(", "from_environment("):
        assert prohibited not in builder_source
