"""Command-line entry point: `python -m tally <command> ...`."""

import argparse
import sys

from tally import parse, report


def cmd_report(args: argparse.Namespace) -> int:
    entries = parse.load(args.file)
    sys.stdout.write(report.render_text(report.totals_by_category(entries)))
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    tags = ";".join(args.tag or [])
    with open(args.file, "a", encoding="utf-8") as f:
        f.write(f"{args.date},{args.amount},{args.category},{tags},{args.memo}\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tally", description="Tiny CSV ledger.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("report", help="print totals per category")
    p.add_argument("file")

    p = sub.add_parser("add", help="append an entry")
    p.add_argument("file")
    p.add_argument("--date", required=True)
    p.add_argument("--amount", required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--tag", action="append")
    p.add_argument("--memo", default="")
    return parser


COMMANDS = {"report": cmd_report, "add": cmd_add}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
