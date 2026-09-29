"""CSV parsing for ledger files. See docs/SPEC.md for the format."""

import csv
import io
import re

from tally.models import Entry

COLUMNS = ["date", "amount", "category", "tags", "memo"]

_PLAIN = re.compile(r"(-?)(\d+)(?:\.(\d{1,2}))?")


def parse_amount(text: str) -> int:
    """Parse a plain decimal amount such as "12.50" or "-3" into cents."""
    m = _PLAIN.fullmatch(text.strip())
    if not m:
        raise ValueError(f"invalid amount: {text!r}")
    sign, whole, frac = m.groups()
    cents = int(whole) * 100 + int((frac or "").ljust(2, "0"))
    return -cents if sign else cents


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
                amount=parse_amount(row["amount"]),
                category=row["category"].strip(),
                tags=parse_tags(row.get("tags") or ""),
                memo=(row.get("memo") or "").strip(),
            )
        )
    return entries


def load(path: str) -> list[Entry]:
    with open(path, encoding="utf-8") as f:
        return parse_csv(f.read())
