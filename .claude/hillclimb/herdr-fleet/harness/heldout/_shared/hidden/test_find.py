from conftest import readme_commands

LEDGER = """
date,amount,category,tags,memo
2026-03-01,12.50,food,,Lunch with Ana
2026-03-02,4.00,food,,coffee
2026-03-03,30.00,travel,,train to lunch meeting
"""


def test_find_ignores_case_in_file_order(tally, ledger):
    r = tally("find", ledger(LEDGER), "LUNCH")
    assert r.code == 0, r.err
    assert r.lines() == ["2026-03-01 12.50 food Lunch with Ana", "2026-03-03 30.00 travel train to lunch meeting"]


def test_find_no_match_exits_1(tally, ledger):
    r = tally("find", ledger(LEDGER), "rent")
    assert r.code == 1
    assert r.lines() == []


def test_readme_lists_find():
    assert "find FILE TEXT" in readme_commands()
