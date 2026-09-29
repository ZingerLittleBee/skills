from tally.dates import month_key, week_of


def test_month_key():
    assert month_key("2026-02-03") == "2026-02"


def test_week_of_iso():
    # 2027-01-01 is a Friday in ISO week 53 of 2026.
    assert week_of("2027-01-01") == "2026-W53"
