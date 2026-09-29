from conftest import readme_commands


def test_tags_counts_sorted(tally, ledger):
    r = tally("tags", ledger("""
date,amount,category,tags,memo
2026-01-01,1.00,a,weekly;groceries,
2026-01-02,1.00,a,groceries,
2026-01-03,1.00,a,bank,
2026-01-04,1.00,a,,
2026-01-05,1.00,a,weekly; alpha ,
"""))
    assert r.code == 0, r.err
    assert r.lines() == ["groceries 2", "weekly 2", "alpha 1", "bank 1"]


def test_existing_commands_still_work(tally, ledger):
    r = tally("report", ledger("date,amount,category,tags,memo\n2026-01-01,2.50,a,x,\n"))
    assert r.code == 0 and "TOTAL" in r.out


def test_readme_lists_tags():
    assert "tags FILE" in readme_commands()
