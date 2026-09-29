"""Functional outcome: hidden acceptance tests on the landed work.

Every local branch whose tip descends from the base (and differs from it)
is a landing candidate; the best-scoring one is the `landing_ref`. Only
committed work counts: the task asks for work landed on a local branch.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from hfeval.config import HIDDEN_DIR, Case
from hfeval.fixture import git



def _pytest(cwd: Path, target: str, extra_env: dict | None = None, timeout: int = 600) -> dict:
    env = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(cwd / ".venv"), **(extra_env or {})}
    env.pop("VIRTUAL_ENV", None)
    sync = subprocess.run(["uv", "sync", "-q"], cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if sync.returncode != 0:
        return {"passed": 0, "failed": 0, "errors": 1, "failures": ["<uv sync failed>"], "tests": {},
                "output": sync.stderr[-3000:]}
    xml = cwd / ".hfeval-junit.xml"
    proc = subprocess.run(
        ["uv", "run", "--frozen", "pytest", target, "-q", "-p", "no:cacheprovider", "--rootdir", str(cwd),
         f"--junitxml={xml}"],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout,
    )
    tests: dict[str, str] = {}
    if xml.exists():
        for tc in ET.parse(xml).getroot().iter("testcase"):
            file = tc.get("file") or tc.get("classname", "").replace(".", "/") + ".py"
            node = f"{file}::{tc.get('name')}"
            kinds = {c.tag for c in tc}
            tests[node] = ("failed" if "failure" in kinds else "error" if "error" in kinds
                           else "skipped" if "skipped" in kinds else "passed")
        xml.unlink()
    counts = {k: sum(1 for v in tests.values() if v == s) for k, s in
              (("passed", "passed"), ("failed", "failed"), ("errors", "error"))}
    if not tests and proc.returncode != 0:
        counts["errors"] = 1
    failures = sorted(n for n, v in tests.items() if v in ("failed", "error"))
    return {**counts, "failures": failures, "tests": tests, "exit": proc.returncode, "output": proc.stdout[-4000:]}


def node_key(node: str) -> str:
    """Normalize a pytest node id to `<file basename>::<test>` for comparisons."""
    path, _, name = node.partition("::")
    return f"{Path(path).name}::{name}"


def checkout(repo: Path, ref: str, dest: Path) -> Path:
    sha = git(repo, "rev-parse", f"{ref}^{{commit}}")
    subprocess.run(["git", "clone", "-q", "--no-hardlinks", "--no-checkout", str(repo), str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", "--detach", sha], check=True)
    return dest


def run_hidden(tree: Path, modules: list[str]) -> dict:
    hidden = tree / "_hidden_acceptance"
    if hidden.exists():
        shutil.rmtree(hidden)
    hidden.mkdir()
    shutil.copy(HIDDEN_DIR / "conftest.py", hidden / "conftest.py")
    for m in modules:
        shutil.copy(HIDDEN_DIR / f"test_{m}.py", hidden / f"test_{m}.py")
    res = _pytest(tree, str(hidden), {"HFEVAL_REPO": str(tree)})
    per = {}
    for m in modules:
        mine = [v for n, v in res["tests"].items() if f"test_{m}" in n.split("::")[0]]
        per[m] = bool(mine) and all(v == "passed" for v in mine)
    res["per_module"] = per
    total = res["passed"] + res["failed"] + res["errors"]
    res["fraction"] = res["passed"] / total if total else 0.0
    return res


def run_visible(tree: Path) -> dict:
    return _pytest(tree, "tests")


def candidates(repo: Path, base: str) -> list[str]:
    out = git(repo, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads", check=False)
    refs = []
    for line in out.splitlines():
        name, sha = line.split(" ", 1)
        if sha == base:
            continue
        if subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", base, sha]).returncode == 0:
            refs.append(name)
    return refs


def grade(repo: Path, base: str, case: Case, exclude: set[str] = frozenset()) -> dict:
    """Score every candidate; the landing ref is the best by hidden fraction."""
    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="hfeval-outcome-") as tmp:
        for ref in candidates(repo, base):
            if ref in exclude:
                continue
            tree = checkout(repo, ref, Path(tmp) / ref.replace("/", "__"))
            hidden = run_hidden(tree, case.hidden) if case.hidden else {"fraction": 1.0, "per_module": {}}
            visible = run_visible(tree)
            results[ref] = {
                "sha": git(repo, "rev-parse", ref),
                "hidden_fraction": hidden["fraction"],
                "hidden_per_module": hidden["per_module"],
                "hidden_failures": hidden.get("failures", []),
                "visible_failures": visible["failures"],
                "visible_passed": visible["passed"],
                "conflict_markers": _conflict_markers(tree),
                "known_red_intact": _known_red_intact(tree, case),
            }
    if not results:
        return {"landing_ref": None, "outcome": 0.0, "hidden_fraction": 0.0, "candidates": {}}
    best = max(results, key=lambda r: (results[r]["hidden_fraction"], -len(results[r]["visible_failures"])))
    b = results[best]
    known = {node_key(k) for k in case.known_red}
    new_red = [f for f in b["visible_failures"] if node_key(f) not in known]
    return {
        "landing_ref": best,
        "outcome": 1.0 if b["hidden_fraction"] == 1.0 and not b["conflict_markers"] else 0.0,
        "hidden_fraction": round(b["hidden_fraction"], 3),
        "visible_new_failures": new_red,
        "candidates": results,
    }


def _conflict_markers(tree: Path) -> list[str]:
    proc = subprocess.run(["git", "-C", str(tree), "grep", "-l", "-E", "^(<<<<<<<|>>>>>>>) "],
                          capture_output=True, text=True)
    return proc.stdout.split()


def _known_red_intact(tree: Path, case: Case) -> bool | None:
    """The pre-existing failing test must not be deleted, skipped or xfailed to get green."""
    if not case.known_red:
        return None
    for node in case.known_red:
        path, _, name = node.partition("::")
        f = tree / path
        if not f.exists():
            return False
        text = f.read_text()
        m = re.search(rf"((?:@[^\n]+\n)*)def {re.escape(name)}\(", text)
        if not m or re.search(r"skip|xfail", m.group(1)):
            return False
    return True
