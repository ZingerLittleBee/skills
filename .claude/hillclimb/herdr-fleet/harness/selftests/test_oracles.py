"""Hidden tests must fail on the base fixture and pass on a reference solution."""

import shutil
import subprocess
from pathlib import Path

import pytest

from hfeval.config import FIXTURE_BASE, ORACLES, load_case
from hfeval.outcome import node_key, run_hidden, run_visible

ORACLE_FOR = {"N1": "a", "F1": "a", "F2a": "a", "F2b": "a", "F3": "a", "R1": "a", "R2": "a",
              "F4": "f4", "N2": "n2"}
IGNORE = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache")


def _tree(tmp_path: Path, case_id: str, oracle: str | None) -> Path:
    case = load_case(case_id)
    tree = tmp_path / "tree"
    shutil.copytree(FIXTURE_BASE, tree, ignore=IGNORE)
    if case.overlay:
        shutil.copytree(case.dir / case.overlay, tree, dirs_exist_ok=True, ignore=IGNORE)
    if oracle:
        shutil.copytree(ORACLES / oracle, tree, dirs_exist_ok=True, ignore=IGNORE)
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    return tree


@pytest.mark.parametrize("case_id", sorted(ORACLE_FOR))
def test_oracle_passes_hidden(tmp_path, case_id):
    case = load_case(case_id)
    res = run_hidden(_tree(tmp_path, case_id, ORACLE_FOR[case_id]), case.hidden)
    assert res["fraction"] == 1.0, res["failures"]


@pytest.mark.parametrize("case_id", sorted(ORACLE_FOR))
def test_base_fails_every_hidden_module(tmp_path, case_id):
    case = load_case(case_id)
    res = run_hidden(_tree(tmp_path, case_id, None), case.hidden)
    passing = [m for m, ok in res["per_module"].items() if ok]
    assert not passing, f"hidden modules already pass on base: {passing}"


def test_f4_base_suite_is_red_only_on_known_red(tmp_path):
    case = load_case("F4")
    res = run_visible(_tree(tmp_path, "F4", None))
    assert [node_key(f) for f in res["failures"]] == [node_key(k) for k in case.known_red]
