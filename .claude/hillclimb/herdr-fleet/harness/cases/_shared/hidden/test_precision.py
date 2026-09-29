from conftest import REPO


def test_household_fees(tally):
    r = tally("report", str(REPO / "examples" / "household.csv"))
    assert r.code == 0, r.err
    assert "fees                    0.29" in r.out
    assert "TOTAL                1260.84" in r.out


def test_many_small_amounts(tally, ledger):
    rows = "".join("2026-01-01,0.01,misc,,\n" for _ in range(100))
    r = tally("report", ledger("date,amount,category,tags,memo\n" + rows))
    assert "misc                    1.00" in r.out


def test_float_edge_values(tally, ledger):
    r = tally("report", ledger("""
date,amount,category,tags,memo
2026-01-01,1.15,a,,
2026-01-01,-0.29,b,,
2026-01-01,0.10,c,,
2026-01-01,0.20,c,,
"""))
    assert "a                       1.15" in r.out
    assert "b                      -0.29" in r.out
    assert "c                       0.30" in r.out
