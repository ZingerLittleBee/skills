"""Shared helpers for hidden acceptance tests.

The grader copies this directory into a scratch clone of the landing ref and
runs pytest from the clone root. Tests drive the CLI as a black box so any
reasonable internal design passes.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(os.environ.get("HFEVAL_REPO", os.getcwd())).resolve()


class Run:
    def __init__(self, proc: subprocess.CompletedProcess):
        self.code = proc.returncode
        self.out = proc.stdout
        self.err = proc.stderr

    def lines(self) -> list[str]:
        return [line.rstrip() for line in self.out.splitlines() if line.strip()]


@pytest.fixture
def tally():
    def run(*args: str) -> Run:
        env = dict(os.environ, PYTHONPATH=str(REPO))
        proc = subprocess.run(
            [sys.executable, "-m", "tally", *args],
            cwd=REPO, env=env, capture_output=True, text=True, timeout=60,
        )
        return Run(proc)

    return run


@pytest.fixture
def ledger(tmp_path):
    def write(text: str, name: str = "ledger.csv") -> str:
        path = tmp_path / name
        path.write_text(text.lstrip("\n"), encoding="utf-8")
        return str(path)

    return write


def readme_commands() -> str:
    """Return README's command table rows joined as one string."""
    text = (REPO / "README.md").read_text(encoding="utf-8")
    return "\n".join(l for l in text.splitlines() if l.lstrip().startswith("|"))
