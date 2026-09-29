from conftest import readme_commands


def test_months_totals_sorted(tally, ledger):
    r = tally("months", ledger("""
date,amount,category,tags,memo
2026-02-03,8.25,food,,
2025-12-31,100.00,rent,,
2026-01-04,0.50,fees,,
2026-02-01,1200.00,rent,,
2026-01-15,-5.00,food,,
"""))
    assert r.code == 0, r.err
    assert r.lines() == ["2025-12 100.00", "2026-01 -4.50", "2026-02 1208.25"]


def test_readme_lists_months():
    assert "months FILE" in readme_commands()
