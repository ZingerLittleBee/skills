import dataclasses

import pytest

from tally import parse
from tally.money import Money


def test_parse_and_format():
    assert Money.parse("12.50 EUR") == Money(1250, "EUR")
    assert Money.parse("12.50") == Money(1250, "USD")
    assert Money(1250, "EUR").format() == "12.50 EUR"
    assert Money(-5, "USD").format() == "-0.05 USD"


def test_addition_same_currency_only():
    assert Money(100, "EUR") + Money(29, "EUR") == Money(129, "EUR")
    with pytest.raises(ValueError):
        Money(100, "EUR") + Money(1, "USD")


def test_frozen():
    m = Money(1, "USD")
    with pytest.raises(dataclasses.FrozenInstanceError if dataclasses.is_dataclass(m) else AttributeError):
        m.cents = 2


def test_entry_amount_is_money():
    (entry,) = parse.parse_csv("date,amount,category,tags,memo\n2026-01-01,0.29,a,,\n")
    assert entry.amount == Money(29, "USD")


def test_add_then_report(tally, ledger):
    path = ledger("date,amount,category,tags,memo\n2026-01-01,10.00,food,,\n")
    assert tally("add", path, "--date", "2026-01-02", "--amount", "2.50", "--category", "food").code == 0
    r = tally("report", path)
    assert r.code == 0, r.err
    assert "food                   12.50" in r.out
