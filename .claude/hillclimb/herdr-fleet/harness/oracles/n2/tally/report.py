"""Totals and text rendering."""

from tally.models import Entry
from tally.money import Money


def totals_by_currency(entries: list[Entry]) -> dict[str, dict[str, Money]]:
    groups: dict[str, dict[str, Money]] = {}
    for e in entries:
        totals = groups.setdefault(e.amount.currency, {})
        totals[e.category] = totals[e.category] + e.amount if e.category in totals else e.amount
    return groups


def render_text(groups: dict[str, dict[str, Money]]) -> str:
    sections = []
    for code in sorted(groups):
        totals = groups[code]
        lines = [f"== {code} =="]
        for category in sorted(totals):
            lines.append(f"{category:<16}{totals[category].amount_text():>12}")
        total = Money(sum(m.cents for m in totals.values()), code)
        lines.append(f"{'TOTAL':<16}{total.amount_text():>12}")
        sections.append("\n".join(lines) + "\n")
    return "\n".join(sections)
