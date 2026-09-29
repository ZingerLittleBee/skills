def test_grouped_by_currency(tally, ledger):
    r = tally("report", ledger("""
date,amount,category,tags,memo,currency
2026-01-01,10.00,food,,,USD
2026-01-02,5.25,food,,,EUR
2026-01-03,1.00,fees,,,EUR
2026-01-04,2.50,rent,,,
"""))
    assert r.code == 0, r.err
    expected = (
        "== EUR ==\n"
        f"{'fees':<16}{'1.00':>12}\n"
        f"{'food':<16}{'5.25':>12}\n"
        f"{'TOTAL':<16}{'6.25':>12}\n"
        "\n"
        "== USD ==\n"
        f"{'food':<16}{'10.00':>12}\n"
        f"{'rent':<16}{'2.50':>12}\n"
        f"{'TOTAL':<16}{'12.50':>12}\n"
    )
    assert r.out.rstrip("\n") == expected.rstrip("\n")


def test_single_currency_has_header(tally, ledger):
    r = tally("report", ledger("date,amount,category,tags,memo\n2026-01-01,3.00,a,,\n"))
    assert r.out.splitlines()[0] == "== USD =="
