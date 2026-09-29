import json

LEDGER = """
date,amount,category,tags,memo
2026-01-01,10.25,food,,
2026-01-02,45.00,transport,commute,
2026-01-03,2.50,food,x,
"""


def test_json_totals(tally, ledger):
    r = tally("report", ledger(LEDGER), "--format", "json")
    assert r.code == 0, r.err
    data = json.loads(r.out)
    assert data == {"categories": {"food": "12.75", "transport": "45.00"}, "total": "57.75"}


def test_text_default_unchanged(tally, ledger):
    path = ledger(LEDGER)
    default = tally("report", path)
    explicit = tally("report", path, "--format", "text")
    assert default.code == 0 and explicit.code == 0
    assert default.out == explicit.out
    assert "food                   12.75" in default.out
    assert "TOTAL                  57.75" in default.out
