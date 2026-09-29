"""Core data types for tally."""

from dataclasses import dataclass, field

from tally.money import Money


@dataclass
class Entry:
    """One ledger line."""

    date: str
    amount: Money
    category: str
    tags: list[str] = field(default_factory=list)
    memo: str = ""
