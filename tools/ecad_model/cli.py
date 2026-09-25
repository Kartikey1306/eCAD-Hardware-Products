"""Command-line interface for CAD dataset items.

    python3 tools/cad_dataset.py build    <item-dir>
    python3 tools/cad_dataset.py check    <item-dir>
    python3 tools/cad_dataset.py validate <item-dir> --output <dir>

build writes every derived file and dataset-item.json from the item's CAD,
annotations and requirements. check exits 1 if any recorded hash is wrong or
any committed derived file no longer reproduces from the CAD. validate runs
V0-V4 and writes a v1 receipt, evidence, a requirement trace and a report; it
exits 0 when the run completed, whatever the verdicts, and 1 only when it
could not produce a receipt.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import dataset


def _cmd_build(args: argparse.Namespace) -> int:
    for relative in dataset.build(Path(args.item)):
        print(f"wrote {Path(args.item) / relative}")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    problems = dataset.check(Path(args.item))
    for problem in problems:
        print(f"drift: {problem}")
    if not problems:
        print(f"{args.item}: every hash matches and every derived file reproduces from the CAD")
    return 1 if problems else 0


def _cmd_validate(args: argparse.Namespace) -> int:
    output = Path(args.output)
    try:
        receipt = dataset.validate(Path(args.item), output)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(
        {
            "product": receipt["product"]["id"],
            "overall_verdict": receipt["overall_verdict"],
            "execution_complete": receipt["execution_complete"],
            "gates": {gate["gate"]: gate["verdict"] for gate in receipt["gates"]},
        },
        indent=2, sort_keys=True,
    ))
    print(f"report: {output / 'report.md'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """The argument parser for build, check and validate.

    Returns:
        An argparse parser whose parsed namespace carries a handler.

    Example:
        >>> build_parser().parse_args(["check", "datasets/cad/robotic_joint_001"]).item
        'datasets/cad/robotic_joint_001'
    """
    parser = argparse.ArgumentParser(description="CAD dataset items: build, check, validate")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, handler, help_text in (
        ("build", _cmd_build, "write derived files and dataset-item.json from the CAD"),
        ("check", _cmd_check, "verify hashes and that derived files reproduce from the CAD"),
        ("validate", _cmd_validate, "run V0-V4 and write a receipt"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("item", help="dataset item directory")
        if name == "validate":
            command.add_argument("--output", required=True, help="empty directory for the receipt and evidence")
        command.set_defaults(handler=handler)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Run one command.

    Args:
        argv: Arguments without the program name; sys.argv[1:] when None.

    Returns:
        The process exit status.

    Example:
        >>> main(["check", str(dataset.REPOSITORY_ROOT / "datasets/cad/robotic_joint_001")])  # doctest: +ELLIPSIS
        /.../datasets/cad/robotic_joint_001: every hash matches and every derived file reproduces from the CAD
        0
    """
    args = build_parser().parse_args(argv)
    return int(args.handler(args))
