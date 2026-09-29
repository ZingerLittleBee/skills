"""CSV parsing for ledger files. See docs/SPEC.md for the format."""

import csv
import io

from tally.models import Entry
from tally.money import Money

COLUMNS = ["date", "amount", "category", "tags", "memo", "currency"]


def parse_amount(text: str, currency: str = "USD") -> Money:
    """Parse a plain decimal amount such as "12.50" or "-3.00"."""
    return Money.parse(text, currency)


def parse_tags(text: str) -> list[str]:
    return [t.strip() for t in text.split(";") if t.strip()]


def parse_csv(text: str) -> list[Entry]:
    """Parse ledger CSV text (with a header row) into entries."""
    reader = csv.DictReader(io.StringIO(text))
    entries = []
    for row in reader:
        entries.append(
            Entry(
                date=row["date"].strip(),
                amount=parse_amount(row["amount"], (row.get("currency") or "").strip() or "USD"),
                category=row["category"].strip(),
                tags=parse_tags(row.get("tags") or ""),
                memo=(row.get("memo") or "").strip(),
            )
        )
    return entries


def load(path: str) -> list[Entry]:
    with open(path, encoding="utf-8") as f:
        return parse_csv(f.read())
