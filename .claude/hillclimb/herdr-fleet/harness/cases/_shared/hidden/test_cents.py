from conftest import REPO

from tally import parse, report


def _cents(entry) -> int:
    for name in ("amount", "amount_cents", "cents"):
        value = getattr(entry, name, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        inner = getattr(value, "cents", None)
        if isinstance(inner, int):
            return inner
    raise AssertionError(f"no integer-cents amount on {entry!r}")


def test_entries_hold_integer_cents():
    entries = parse.parse_csv("date,amount,category,tags,memo\n2026-01-01,0.29,a,,\n2026-01-02,-12.5,a,,\n")
    assert [_cents(e) for e in entries] == [29, -1250]


def test_totals_are_integers():
    entries = parse.parse_csv("date,amount,category,tags,memo\n2026-01-01,0.10,a,,\n2026-01-02,0.20,a,,\n")
    totals = report.totals_by_category(entries)
    value = totals["a"]
    assert (value if isinstance(value, int) else getattr(value, "cents", None)) == 30


def test_household_report_exact(tally):
    r = tally("report", str(REPO / "examples" / "household.csv"))
    assert "fees                    0.29" in r.out
    assert "TOTAL                1260.84" in r.out
