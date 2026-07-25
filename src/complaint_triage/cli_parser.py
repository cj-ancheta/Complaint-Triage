"""Argument-parser construction for the public complaint-triage CLI."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="complaint-triage")
    subcommands = parser.add_subparsers(dest="command", required=True)
    _add_data_commands(subcommands)
    _add_baseline_commands(subcommands)
    _add_transformer_commands(subcommands)
    return parser


def _add_data_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    subcommands.add_parser(
        "profile-cfpb", help="Run one fixed, five-hit CFPB source-contract check."
    )
    ingest = subcommands.add_parser(
        "ingest-raw-batch", help="Validate and load one content-addressed CFPB raw batch."
    )
    ingest.add_argument(
        "--manifest", type=Path, required=True, help="Manifest under data/manifests/cfpb/."
    )
    stage = subcommands.add_parser(
        "stage-raw-batch", help="Create versioned staging outcomes for one ingested raw batch."
    )
    stage.add_argument("--batch-id", required=True, help="Raw ingestion batch ID.")
    subcommands.add_parser(
        "profile-taxonomy", help="Run the fixed aggregate-only CFPB taxonomy stability profile."
    )
    population = subcommands.add_parser(
        "report-population", help="Create a versioned aggregate analytical-population report."
    )
    population.add_argument("--batch-id", required=True, help="Staged raw batch ID.")
    cleanup = subcommands.add_parser(
        "cleanup-real-data",
        help="Inventory an extraction run, or delete it with exact confirmation.",
    )
    cleanup.add_argument("--run-manifest", type=Path, required=True)
    cleanup.add_argument("--execute", action="store_true")
    cleanup.add_argument("--confirmation")
    acquire = subcommands.add_parser(
        "acquire-real-run", help="Acquire the approved retained CFPB run from a clean commit."
    )
    acquire.add_argument(
        "--confirmation", required=True, help="Must exactly match the accepted retention policy ID."
    )
    _path_command(
        subcommands,
        "report-real-run",
        "Reconcile and publish an aggregate-only report for one real run.",
        "--run-manifest",
    )
    _path_command(
        subcommands,
        "build-temporal-split",
        "Build the approved deduplicated temporal split for one real run.",
        "--run-manifest",
    )


def _add_baseline_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    _path_command(
        subcommands,
        "evaluate-majority-baseline",
        "Evaluate the training-majority reference against the accepted split.",
        "--split-manifest",
    )
    tfidf = _path_command(
        subcommands,
        "train-tfidf-logreg",
        "Run the approved validation-only TF-IDF logistic search.",
        "--split-manifest",
    )
    tfidf.add_argument(
        "--smoke",
        action="store_true",
        help="Fit a bounded training-only sample without writing evidence.",
    )
    _path_command(
        subcommands,
        "analyze-baseline-errors",
        "Produce validation-only aggregate error analysis for the selected baseline.",
        "--model-report",
    )


def _add_transformer_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    commands = (
        (
            "profile-transformer-tokens",
            "Profile pinned MiniLM token lengths using training narratives only.",
            "--split-manifest",
        ),
        (
            "validate-transformer-dataset",
            "Validate deterministic train/validation tokenization and dynamic padding.",
            "--split-manifest",
        ),
        (
            "smoke-transformer-training",
            "Run approved synthetic-memory and training-only MiniLM smokes.",
            "--split-manifest",
        ),
        (
            "train-transformer",
            "Run the approved validation-only MiniLM fit and epoch selection.",
            "--split-manifest",
        ),
        (
            "calibrate-transformer",
            "Fit approved September temperature scaling and assess October validation.",
            "--transformer-report",
        ),
        (
            "select-operational-model",
            "Run the approved CT-306 CPU benchmark and operational model decision.",
            "--calibration-report",
        ),
        (
            "analyze-abstention",
            "Evaluate the approved validation-only abstention threshold grid.",
            "--model-selection-report",
        ),
    )
    for name, help_text, argument in commands:
        _path_command(subcommands, name, help_text, argument)
    comparison = subcommands.add_parser(
        "compare-validation-models", help="Compare accepted TF-IDF and MiniLM validation evidence."
    )
    comparison.add_argument("--baseline-report", type=Path, required=True)
    comparison.add_argument("--transformer-report", type=Path, required=True)


def _path_command(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    help_text: str,
    argument: str,
) -> argparse.ArgumentParser:
    command = subcommands.add_parser(name, help=help_text)
    command.add_argument(argument, type=Path, required=True)
    return command
