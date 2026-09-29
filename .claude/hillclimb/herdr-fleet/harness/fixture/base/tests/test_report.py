from tally.models import Entry
from tally.report import format_amount, render_text, totals_by_category


def test_totals_group_by_category():
    entries = [
        Entry("2026-01-01", 10.0, "food"),
        Entry("2026-01-02", 5.0, "food"),
        Entry("2026-01-03", 45.0, "transport"),
    ]
    assert totals_by_category(entries) == {"food": 15.0, "transport": 45.0}


def test_format_amount_two_decimals():
    assert format_amount(12.5) == "12.50"
    assert format_amount(1200) == "1200.00"


def test_render_text_layout():
    out = render_text({"food": 15.0, "transport": 45.0})
    assert out.splitlines() == [
        "food                   15.00",
        "transport              45.00",
        "TOTAL                  60.00",
    ]
