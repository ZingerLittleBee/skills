"""Exact money amounts."""

import re
from dataclasses import dataclass

_TEXT = re.compile(r"(-?)(\d+)(?:\.(\d{1,2}))?(?:\s+([A-Z]{3}))?")


@dataclass(frozen=True)
class Money:
    cents: int
    currency: str = "USD"

    @classmethod
    def parse(cls, text: str, currency: str = "USD") -> "Money":
        m = _TEXT.fullmatch(text.strip())
        if not m:
            raise ValueError(f"invalid amount: {text!r}")
        sign, whole, frac, code = m.groups()
        cents = int(whole) * 100 + int((frac or "").ljust(2, "0"))
        return cls(-cents if sign else cents, code or currency)

    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        if other.currency != self.currency:
            raise ValueError(f"cannot add {self.currency} and {other.currency}")
        return Money(self.cents + other.cents, self.currency)

    def amount_text(self) -> str:
        sign = "-" if self.cents < 0 else ""
        return f"{sign}{abs(self.cents) // 100}.{abs(self.cents) % 100:02d}"

    def format(self) -> str:
        return f"{self.amount_text()} {self.currency}"
