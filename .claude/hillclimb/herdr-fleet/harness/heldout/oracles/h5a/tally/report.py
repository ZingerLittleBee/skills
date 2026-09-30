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
    for category in sorted(totals, key=lambda c: (-totals[c], c)):
        lines.append(f"{category:<16}{format_amount(totals[category]):>12}")
    lines.append(f"{'TOTAL':<16}{format_amount(sum(totals.values())):>12}")
    return "\n".join(lines) + "\n"


def stats(entries: list[Entry]) -> list[str]:
    amounts = [e.amount for e in entries]
    return [f"entries {len(amounts)}", f"largest {format_amount(max(amounts))}",
            f"smallest {format_amount(min(amounts))}"]


def find(entries: list[Entry], text: str) -> list[str]:
    needle = text.lower()
    return [f"{e.date} {format_amount(e.amount)} {e.category} {e.memo}" for e in entries if needle in e.memo.lower()]
