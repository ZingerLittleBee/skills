"""Core data types for tally."""

from dataclasses import dataclass, field


@dataclass
class Entry:
    """One ledger line. `amount` is in integer cents."""

    date: str
    amount: int
    category: str
    tags: list[str] = field(default_factory=list)
    memo: str = ""
