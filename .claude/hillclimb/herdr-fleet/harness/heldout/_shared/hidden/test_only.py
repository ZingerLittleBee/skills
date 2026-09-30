LEDGER = """
date,amount,category,tags,memo
2026-03-01,12.50,food,,
2026-03-02,-5.00,refund,,
2026-03-03,100.00,rent,,
2026-03-04,3.25,food,,
"""


def _rows(run) -> list[list[str]]:
    return [line.split() for line in run.lines()]


def test_only_one_category(tally, ledger):
    r = tally("report", ledger(LEDGER), "--only", "food")
    assert r.code == 0, r.err
    assert _rows(r) == [["food", "15.75"], ["TOTAL", "15.75"]]


def test_only_repeated(tally, ledger):
    r = tally("report", ledger(LEDGER), "--only", "rent", "--only", "food")
    assert r.code == 0, r.err
    assert _rows(r) == [["food", "15.75"], ["rent", "100.00"], ["TOTAL", "115.75"]]


def test_only_absent_category(tally, ledger):
    r = tally("report", ledger(LEDGER), "--only", "travel")
    assert r.code == 0, r.err
    assert _rows(r) == [["TOTAL", "0.00"]]


def test_without_only_unchanged(tally, ledger):
    r = tally("report", ledger(LEDGER))
    assert r.code == 0, r.err
    assert _rows(r) == [["food", "15.75"], ["refund", "-5.00"], ["rent", "100.00"], ["TOTAL", "110.75"]]
