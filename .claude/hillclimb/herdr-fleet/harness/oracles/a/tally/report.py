"""Totals and text rendering."""

import json

from tally.models import Entry


def totals_by_category(entries: list[Entry]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for e in entries:
        totals[e.category] = totals.get(e.category, 0.0) + e.amount
    return totals


def format_amount(value: float) -> str:
    """Render an amount with two decimals, rounded to the nearest cent."""
    cents = round(value * 100)
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def render_text(totals: dict[str, float]) -> str:
    lines = []
    for category in sorted(totals):
        lines.append(f"{category:<16}{format_amount(totals[category]):>12}")
    lines.append(f"{'TOTAL':<16}{format_amount(sum(totals.values())):>12}")
    return "\n".join(lines) + "\n"


def render_json(totals: dict[str, float]) -> str:
    data = {
        "categories": {c: format_amount(totals[c]) for c in sorted(totals)},
        "total": format_amount(sum(totals.values())),
    }
    return json.dumps(data) + "\n"


def tag_counts(entries: list[Entry]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for e in entries:
        for tag in e.tags:
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def month_totals(entries: list[Entry]) -> list[tuple[str, float]]:
    totals: dict[str, float] = {}
    for e in entries:
        totals[e.date[:7]] = totals.get(e.date[:7], 0.0) + e.amount
    return sorted(totals.items())
