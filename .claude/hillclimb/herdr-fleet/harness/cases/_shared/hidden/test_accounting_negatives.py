def test_accounting_negatives(tally, ledger):
    r = tally("report", ledger('''
date,amount,category,tags,memo
2026-01-01,(12.50),a,,
2026-01-02,"(1,234.25)",b,,
2026-01-03,20.00,a,,
'''))
    assert r.code == 0, r.err
    assert "a                       7.50" in r.out
    assert "b                   -1234.25" in r.out
