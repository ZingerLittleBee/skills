"""Core data types for tally."""

from dataclasses import dataclass, field


@dataclass
class Entry:
    """One ledger line."""

    date: str
    amount: float
    category: str
    tags: list[str] = field(default_factory=list)
    memo: str = ""
