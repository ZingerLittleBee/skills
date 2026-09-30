from conftest import readme_commands

LEDGER = """
date,amount,category,tags,memo
2026-03-01,12.50,food,,lunch
2026-03-02,-5.00,refund,,
2026-03-03,100.00,rent,,
2026-03-04,3.25,food,,
"""


def test_stats_lines(tally, ledger):
    r = tally("stats", ledger(LEDGER))
    assert r.code == 0, r.err
    assert r.lines() == ["entries 4", "largest 100.00", "smallest -5.00"]


def test_stats_single_entry(tally, ledger):
    r = tally("stats", ledger("date,amount,category,tags,memo\n2026-03-01,7.75,food,,\n"))
    assert r.code == 0, r.err
    assert r.lines() == ["entries 1", "largest 7.75", "smallest 7.75"]


def test_readme_lists_stats():
    assert "stats FILE" in readme_commands()
