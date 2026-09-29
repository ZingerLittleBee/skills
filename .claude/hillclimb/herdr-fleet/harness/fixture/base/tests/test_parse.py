from tally.parse import parse_amount, parse_csv, parse_tags


def test_parse_plain_amounts():
    assert parse_amount("12.50") == 12.5
    assert parse_amount("-3.00") == -3.0
    assert parse_amount(" 7 ") == 7.0


def test_parse_tags_skips_blanks():
    assert parse_tags("a; b;;c ") == ["a", "b", "c"]
    assert parse_tags("") == []


def test_parse_csv_reads_all_columns():
    text = "date,amount,category,tags,memo\n2026-01-03,12.10,food,groceries;weekly,market\n"
    [entry] = parse_csv(text)
    assert entry.date == "2026-01-03"
    assert entry.amount == 12.10
    assert entry.category == "food"
    assert entry.tags == ["groceries", "weekly"]
    assert entry.memo == "market"


def test_parse_csv_optional_columns_may_be_empty():
    [entry] = parse_csv("date,amount,category,tags,memo\n2026-02-01,1200.00,rent,,\n")
    assert entry.tags == []
    assert entry.memo == ""
