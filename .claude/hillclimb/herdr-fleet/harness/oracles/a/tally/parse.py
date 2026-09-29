"""CSV parsing for ledger files. See docs/SPEC.md for the format."""

import csv
import io
import re

from tally.models import Entry

COLUMNS = ["date", "amount", "category", "tags", "memo"]

_AMOUNT = re.compile(r"-?(\d{1,3}(,\d{3})+|\d+)(\.\d{1,2})?")


def parse_amount(text: str) -> float:
    """Parse an amount in any spelling allowed by docs/SPEC.md."""
    raw = text.strip()
    body, sign = raw, 1
    if raw.startswith("(") and raw.endswith(")"):
        body, sign = raw[1:-1], -1
        if body.startswith("-"):
            raise ValueError(f"invalid amount: {text!r}")
    if not _AMOUNT.fullmatch(body):
        raise ValueError(f"invalid amount: {text!r}")
    return sign * float(body.replace(",", ""))


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
