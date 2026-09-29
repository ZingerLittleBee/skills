from conftest import REPO


def _version() -> str:
    ns: dict = {}
    for line in (REPO / "tally" / "__init__.py").read_text().splitlines():
        if line.startswith("__version__"):
            exec(line, ns)
    return ns["__version__"]


def test_version_flag(tally):
    r = tally("--version")
    assert r.code == 0, r.err
    assert r.out.strip() == f"tally {_version()}"


def test_commands_unaffected(tally, ledger):
    r = tally("report", ledger("date,amount,category,tags,memo\n2026-01-01,2.50,a,,\n"))
    assert r.code == 0 and "TOTAL" in r.out
