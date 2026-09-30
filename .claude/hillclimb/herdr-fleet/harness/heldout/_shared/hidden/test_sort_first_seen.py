LEDGER = """
date,amount,category,tags,memo
2026-01-01,1.00,b,,
2026-01-02,5.00,c,,
2026-01-03,3.00,a,,
2026-01-04,2.00,d,,
2026-01-05,1.00,e,,
2026-01-06,0.50,b,,
"""


def test_report_first_seen_order(tally, ledger):
    r = tally("report", ledger(LEDGER))
    assert r.code == 0, r.err
    assert [line.split()[0] for line in r.lines()] == ["b", "c", "a", "d", "e", "TOTAL"]
