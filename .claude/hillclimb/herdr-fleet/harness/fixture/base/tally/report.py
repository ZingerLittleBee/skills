"""Totals and text rendering."""

from tally.models import Entry


def totals_by_category(entries: list[Entry]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for e in entries:
        totals[e.category] = totals.get(e.category, 0.0) + e.amount
    return totals


def format_amount(value: float) -> str:
    """Render an amount with two decimals."""
    cents = int(value * 100)
    return f"{cents / 100:.2f}"


def render_text(totals: dict[str, float]) -> str:
    lines = []
    for category in sorted(totals):
        lines.append(f"{category:<16}{format_amount(totals[category]):>12}")
    lines.append(f"{'TOTAL':<16}{format_amount(sum(totals.values())):>12}")
    return "\n".join(lines) + "\n"
