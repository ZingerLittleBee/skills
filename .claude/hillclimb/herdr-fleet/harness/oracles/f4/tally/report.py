"""Totals and text rendering."""

import csv
import io

from tally.models import Entry
from tally.parse import COLUMNS


def totals_by_category(entries: list[Entry]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for e in entries:
        totals[e.category] = totals.get(e.category, 0) + e.amount
    return totals


def format_amount(cents: int) -> str:
    """Render integer cents with two decimals."""
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def render_text(totals: dict[str, int]) -> str:
    lines = []
    for category in sorted(totals):
        lines.append(f"{category:<16}{format_amount(totals[category]):>12}")
    lines.append(f"{'TOTAL':<16}{format_amount(sum(totals.values())):>12}")
    return "\n".join(lines) + "\n"


def render_csv(entries: list[Entry]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for e in entries:
        writer.writerow([e.date, format_amount(e.amount), e.category, ";".join(e.tags), e.memo])
    return out.getvalue()
