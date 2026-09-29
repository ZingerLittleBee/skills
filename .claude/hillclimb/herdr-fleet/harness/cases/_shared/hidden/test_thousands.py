import pytest

from tally import parse


def test_thousands_in_report(tally, ledger):
    r = tally("report", ledger('''
date,amount,category,tags,memo
2026-01-01,"1,234.50",rent,,
2026-01-02,"-1,000.25",rent,,
2026-01-03,"12,345,678.00",big,,
'''))
    assert r.code == 0, r.err
    assert "rent                  234.25" in r.out
    assert "big              12345678.00" in r.out


def test_plain_still_parses(tally, ledger):
    r = tally("report", ledger("date,amount,category,tags,memo\n2026-01-01,7,a,,\n"))
    assert "a                       7.00" in r.out


@pytest.mark.parametrize("bad", ["abc", "1.2.3", "12.345"])
def test_invalid_amount_raises(bad):
    with pytest.raises(ValueError):
        parse.parse_csv(f'date,amount,category,tags,memo\n2026-01-01,"{bad}",a,,\n')
