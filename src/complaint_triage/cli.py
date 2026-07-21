"""Command-line entry points for the complaint triage project."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from complaint_triage.cfpb_profile import ProfileError, fetch_cfpb_profile, safe_error_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="complaint-triage")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "profile-cfpb",
        help="Run one fixed, five-hit CFPB source-contract check.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "profile-cfpb":
        try:
            report = fetch_cfpb_profile()
        except ProfileError as error:
            print(json.dumps(safe_error_report(error), indent=2, sort_keys=True))
            return 1

        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")
