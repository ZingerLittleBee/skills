"""Command-line entry point: `python -m tally <command> ...`."""

import argparse
import sys

import tally
from tally import parse, report


def cmd_report(args: argparse.Namespace) -> int:
    totals = report.totals_by_category(parse.load(args.file))
    render = report.render_json if args.format == "json" else report.render_text
    sys.stdout.write(render(totals))
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    tags = ";".join(args.tag or [])
    with open(args.file, "a", encoding="utf-8") as f:
        f.write(f"{args.date},{args.amount},{args.category},{tags},{args.memo}\n")
    return 0


def cmd_tags(args: argparse.Namespace) -> int:
    for tag, count in report.tag_counts(parse.load(args.file)):
        print(f"{tag} {count}")
    return 0


def cmd_months(args: argparse.Namespace) -> int:
    for month, total in report.month_totals(parse.load(args.file)):
        print(f"{month} {report.format_amount(total)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tally", description="Tiny CSV ledger.")
    parser.add_argument("--version", action="version", version=f"tally {tally.__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("report", help="print totals per category")
    p.add_argument("file")
    p.add_argument("--format", choices=["text", "json"], default="text")

    p = sub.add_parser("add", help="append an entry")
    p.add_argument("file")
    p.add_argument("--date", required=True)
    p.add_argument("--amount", required=True)
    p.add_argument("--category", required=True)
    p.add_argument("--tag", action="append")
    p.add_argument("--memo", default="")

    p = sub.add_parser("tags", help="count entries per tag")
    p.add_argument("file")

    p = sub.add_parser("months", help="print totals per month")
    p.add_argument("file")
    return parser


COMMANDS = {"report": cmd_report, "add": cmd_add, "tags": cmd_tags, "months": cmd_months}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
