from conftest import REPO

from tally import parse


def test_currency_column_optional():
    entries = parse.parse_csv(
        "date,amount,category,tags,memo,currency\n"
        "2026-01-01,1.00,a,,,EUR\n"
        "2026-01-02,2.00,a,,,\n"
    )
    assert [e.amount.currency for e in entries] == ["EUR", "USD"]


def test_missing_column_defaults_usd():
    (entry,) = parse.parse_csv("date,amount,category,tags,memo\n2026-01-01,1.00,a,,\n")
    assert entry.amount.currency == "USD"


def test_spec_documents_currency():
    assert "`currency`" in (REPO / "docs" / "SPEC.md").read_text(encoding="utf-8")
