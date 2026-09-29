from pathlib import Path

from tally.cli import main

SAMPLE = "date,amount,category,tags,memo\n2026-01-01,10.00,food,,\n2026-01-02,45.00,transport,commute,\n"


def test_report_command(tmp_path: Path, capsys):
    ledger = tmp_path / "l.csv"
    ledger.write_text(SAMPLE)
    assert main(["report", str(ledger)]) == 0
    assert "TOTAL                  55.00" in capsys.readouterr().out


def test_add_command_appends(tmp_path: Path, capsys):
    ledger = tmp_path / "l.csv"
    ledger.write_text(SAMPLE)
    main(["add", str(ledger), "--date", "2026-01-03", "--amount", "2.50", "--category", "food", "--tag", "x"])
    main(["report", str(ledger)])
    assert "food                   12.50" in capsys.readouterr().out
