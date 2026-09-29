import csv
import io

from conftest import readme_commands


def test_export_canonical(tally, ledger):
    r = tally("export", ledger("""
date,amount,category,tags,memo
2026-01-01,7,food, weekly ; groceries ,market run
2026-01-02,-3.5,fees,,
2026-01-03,1200.25,rent,home,
"""))
    assert r.code == 0, r.err
    assert r.out.splitlines()[0] == "date,amount,category,tags,memo"
    rows = list(csv.DictReader(io.StringIO(r.out)))
    assert [(x["date"], x["amount"], x["category"], x["tags"], x["memo"]) for x in rows] == [
        ("2026-01-01", "7.00", "food", "weekly;groceries", "market run"),
        ("2026-01-02", "-3.50", "fees", "", ""),
        ("2026-01-03", "1200.25", "rent", "home", ""),
    ]


def test_readme_lists_export():
    assert "export FILE" in readme_commands()
