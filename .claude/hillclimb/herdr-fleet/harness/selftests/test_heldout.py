"""Held-out set: separation from the iteration set, hidden tests against
reference solutions, injectors against stand-in processes, and every
held-out fault grader against synthetic rounds. No paid calls."""

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import yaml

from hfeval import fleet, inject, ledger, orchestrate, outcome
from hfeval.config import (CASES_DIR, FIXTURE_BASE, HELDOUT_ORACLES, all_cases, catalog_path, heldout_cases,
                           hidden_module, load_case, load_tasks)
from hfeval.fixture import Attempt, git
from hfeval.trace import OrchestratorTrace, ToolCall

IGNORE = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache")
HELDOUT_IDS = ["H1", "H2", "H3", "H4", "H5", "H6"]


# ------------------------------------------------------------- separation ---

def test_heldout_is_separate_from_iteration_set():
    assert not any(c.heldout for c in all_cases())
    assert [c.id for c in heldout_cases()] == HELDOUT_IDS
    assert not set(HELDOUT_IDS) & {p.name for p in CASES_DIR.iterdir()}
    shared = yaml.safe_load((CASES_DIR / "_shared" / "tasks.yaml").read_text())
    for c in heldout_cases():
        assert c.heldout and "heldout" in c.tags
        assert all(t in load_tasks() for t in c.tasks)
        assert all(hidden_module(m) for m in c.hidden + c.fault.get("exclusive", []))
        assert catalog_path(c.catalog).exists()
        if c.reply_catalog:
            assert catalog_path(c.reply_catalog).exists()
        # Held-out tasks are new work, except where a case needs a shared filler.
        assert not set(c.tasks) & set(shared), c.id


def test_heldout_flow_guard(tmp_path, monkeypatch):
    from hfeval import cli
    monkeypatch.setattr(cli, "_gate", lambda flow: None)
    monkeypatch.setattr(cli, "flow_dir", lambda flow: tmp_path / flow)
    with pytest.raises(SystemExit, match="held-out cases run only"):
        cli.main(["run", "--flow", "herdr-fleet", "--cases", "H1"])
    with pytest.raises(SystemExit, match="held-out cases run only"):
        cli.main(["run", "--flow", "herdr-fleet-heldout", "--cases", "N1"])


# ------------------------------------------------------ oracles and hidden ---

def _tree(tmp_path: Path, *oracles: str) -> Path:
    tree = tmp_path / "tree"
    shutil.copytree(FIXTURE_BASE, tree, ignore=IGNORE)
    for o in oracles:
        shutil.copytree(HELDOUT_ORACLES / o, tree, dirs_exist_ok=True, ignore=IGNORE)
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    return tree


@pytest.mark.parametrize("case_id", HELDOUT_IDS)
def test_heldout_hidden_fail_on_base(tmp_path, case_id):
    case = load_case(case_id)
    res = outcome.run_hidden(_tree(tmp_path), case.hidden + case.fault.get("exclusive", []))
    assert not [m for m, ok in res["per_module"].items() if ok]


@pytest.mark.parametrize("case_id", ["H1", "H2", "H3", "H4", "H6"])
def test_heldout_oracle_passes(tmp_path, case_id):
    tree = _tree(tmp_path, "h")
    assert outcome.run_hidden(tree, load_case(case_id).hidden)["fraction"] == 1.0
    assert not outcome.run_visible(tree)["failures"]


@pytest.mark.parametrize("winner,loser,overlay", [("sort_amount", "sort_first_seen", "h5a"),
                                                   ("sort_first_seen", "sort_amount", "h5b")])
def test_h5_requests_are_mutually_exclusive(tmp_path, winner, loser, overlay):
    tree = _tree(tmp_path, "h", overlay)
    per = outcome.run_hidden(tree, ["stats", winner, loser])["per_module"]
    assert per == {"stats": True, winner: True, loser: False}
    assert not outcome.run_visible(tree)["failures"]


# -------------------------------------------------------------- injectors ---

class StubSession:
    def __init__(self, agents, process_info=None, proc=None):
        self.agents, self.process_info, self.proc = agents, process_info or {}, proc

    def call(self, *args, **_):
        if args[:2] == ("agent", "list"):
            return {"result": {"agents": self.agents}}
        if args[:2] == ("pane", "process-info"):
            return {"result": {"process_info": self.process_info}}
        return {}


def _attempt(tmp_path: Path) -> Attempt:
    a = Attempt(tmp_path / "attempt")
    for d in (a.logs, a.tmp, a.state, a.worktrees, a.xdg_config / "herdr-fleet"):
        d.mkdir(parents=True)
    return a


def _job_parent():
    """A shell whose background job runs in its own process group, like an
    agent CLI under a pane's shell."""
    parent = subprocess.Popen(["bash", "-c", "set -m; sleep 60 & echo $!; wait"], stdout=subprocess.PIPE, text=True)
    return parent, int(parent.stdout.readline())


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()[:1] != "Z"


def test_kill_agent_kills_only_descendant_implementers(tmp_path):
    a = _attempt(tmp_path)
    parent, job = _job_parent()
    try:
        agents = [{"name": "stats-review", "agent_status": "working", "pane_id": "w1:p2"},
                  {"name": "stats", "agent_status": "working", "pane_id": "w1:p1"}]
        info = {"foreground_process_group_id": job, "shell_pid": parent.pid,
                "foreground_processes": [{"pid": job, "cmdline": "sleep 60"}]}
        stop = threading.Event()
        # Not a descendant of the session's server: refused.
        outsider = subprocess.Popen(["sleep", "60"])
        inject.kill_agent(a, StubSession(agents, info, proc=outsider), {"min_working_s": 0, "poll_s": 0.05}, _stop_after(stop, 0.5))
        outsider.kill()
        assert _alive(job)
        assert inject.read_log(a, inject.INJECTOR_LOG)[0]["action"] == "skipped"
        inject.kill_agent(a, StubSession(agents, info, proc=parent), {"min_working_s": 0, "poll_s": 0.05}, threading.Event())
        time.sleep(0.3)
        assert not _alive(job)
        killed = [r for r in inject.read_log(a, inject.INJECTOR_LOG) if r["action"] == "killed"]
        assert [r["agent"] for r in killed] == ["stats"]
    finally:
        parent.kill()


def _stop_after(stop: threading.Event, seconds: float) -> threading.Event:
    threading.Timer(seconds, stop.set).start()
    return stop


def test_corrupt_verdict_truncates_once_while_reviewer_works(tmp_path):
    a = _attempt(tmp_path)
    rd = a.tmp / "herdr-fleet-r1"
    rd.mkdir()
    session = StubSession([{"name": "stats-review", "agent_status": "working"}, {"name": "stats", "agent_status": "idle"}])
    th = threading.Thread(target=inject.corrupt_verdict, args=(a, session, {}, threading.Event()), daemon=True)
    th.start()
    body = json.dumps({"candidate_sha": "abc", "overall_correctness": "correct", "findings": []})
    (rd / "stats-verdict-abc.json").write_text(body[:10])  # partial write: left alone
    time.sleep(0.5)
    (rd / "stats-verdict-abc.json").write_text(body)
    th.join(timeout=5)
    text = (rd / "stats-verdict-abc.json").read_text()
    assert text == body[: len(body) // 2]
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)
    rows = inject.read_log(a, inject.INJECTOR_LOG)
    assert len(rows) == 1 and rows[0]["reviewer_working"] is True and rows[0]["slug"] == "stats"


def _repo_with_worktree_commit(a: Attempt) -> str:
    a.repo.mkdir()
    git(a.repo, "init", "-q", "-b", "main")
    (a.repo / "f").write_text("x\n")
    git(a.repo, "add", "-A")
    git(a.repo, "commit", "-q", "-m", "base")
    base = git(a.repo, "rev-parse", "HEAD")
    wt = a.worktrees / "repo" / "feat-x"
    git(a.repo, "worktree", "add", "-q", "-b", "feat/x", str(wt))
    (wt / "g").write_text("y\n")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "work")
    a.write_meta(base_sha=base)
    return base


def test_interrupt_fires_on_commit_and_working_agent(tmp_path):
    a = _attempt(tmp_path)
    _repo_with_worktree_commit(a)
    proc = subprocess.Popen(["sleep", "60"], start_new_session=True)
    fired: dict = {}
    inject.interrupt_when_ready(a, StubSession([{"name": "x", "agent_status": "working"}]), proc,
                                {"pause_s": 1, "poll_s": 0.1}, fired)
    assert proc.wait(timeout=5) == -signal.SIGKILL
    assert fired["pause_s"] == 1 and fired["working_agents"] == ["x"]


def _manifest(rd: Path, records: list[dict]) -> None:
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))


def _rec(seq, event, key, *, kind="agent", role="package-implementer", status="live", observed=None, rid="r-1"):
    return {"schema_version": 3, "round_id": rid, "round_slug": "t", "seq": seq, "event": event, "resource_key": key,
            "kind": kind, "role": role, "parent_key": key.rsplit("/", 1)[0], "cleanup_policy": "close-aux",
            "selector": {}, "observed": observed or {}, "status": status, "detail": ""}


def test_swap_catalog_records_ledger_position(tmp_path):
    a = _attempt(tmp_path)
    (a.xdg_config / "herdr-fleet" / "slots.yml").write_text(catalog_path("review-dead").read_text())
    _manifest(a.tmp / "herdr-fleet-t", [_rec(1, "intent", "package/stats/impl"), _rec(2, "created", "package/stats/impl")])
    row = inject.swap_catalog(a, "review-dead-fixed")
    assert row["ledger_max_seq"] == 2
    cat = yaml.safe_load((a.xdg_config / "herdr-fleet" / "slots.yml").read_text())
    assert "claude-sonnet-5-medium" in cat["slots"]["review"]


# ------------------------------------------------ orchestrator turn loop ---

FAKE_CLAUDE = r"""#!/usr/bin/env python3
import json, sys, time
msg = sys.stdin.read()
print(json.dumps({"type": "system", "subtype": "init", "session_id": "s-1", "model": "fake"}), flush=True)
if "Please do these tasks" in msg and "--resume" not in sys.argv:
    time.sleep(30)  # cut off by the harness
text = "Which slot should reviews use?" if "cut off" in msg else "Round closed."
print(json.dumps({"type": "result", "subtype": "success", "result": text, "session_id": "s-1",
                  "total_cost_usd": 0.01}), flush=True)
"""


def test_turn_loop_resumes_after_interrupt_and_swaps_catalog(tmp_path, monkeypatch):
    a = _attempt(tmp_path)
    _repo_with_worktree_commit(a)
    (a.xdg_config / "herdr-fleet" / "slots.yml").write_text(catalog_path("review-dead").read_text())
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "claude").write_text(FAKE_CLAUDE)
    (bindir / "claude").chmod(0o755)
    (a.logs / "sandbox.sb").write_text("(version 1)\n(allow default)\n")
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    session = StubSession([{"name": "stats", "agent_status": "working"}])
    session.socket = tmp_path / "sock"
    case = load_case("H4")
    case.interrupt = {**case.interrupt, "pause_s": 1, "poll_s": 1}
    case.reply_catalog = "review-dead-fixed"
    monkeypatch.setattr(orchestrate, "_round_open", lambda att, s, w, text: text.endswith("?"))
    run = orchestrate.run(a, session, case, "Repository: tally. Please do these tasks: ...", with_skill=False,
                          wall_clock_s=120, budget_usd=5, model=None)
    assert [t["interrupted"] for t in run.turns] == [True, False, False]
    assert run.turns[1]["user_message"] == case.interrupt["message"]
    assert run.turns[2]["user_message"] == case.user_reply
    assert run.user_turns == 1 and len(run.interrupts) == 1
    assert inject.read_log(a, inject.CATALOG_LOG)[0]["catalog"] == "review-dead-fixed"


# ---------------------------------------------------------- fault graders ---

def _ctx(a: Attempt, case_id: str, *, records=(), agents=(), verdicts=(), out=None, integrity=1.0, tr=None,
         cleanup=1.0, after=None, routing_problems=None, dirs=()) -> fleet.FaultContext:
    rnd = fleet.Round(dirs=list(dirs), records=list(records), verdicts=list(verdicts), report=ledger.LedgerReport())
    return fleet.FaultContext(
        case=load_case(case_id), attempt=a, rnd=rnd, base="0" * 40, out=out or {"outcome": 1.0, "candidates": {}},
        violations=set(), routing={"agents": list(agents), "routing_problems": routing_problems or {}},
        integrity={"review_integrity": integrity}, user_turns=0, tr=tr, cleanup={"cleanup": cleanup},
        after=after or {})


def _agent(name, seq, *, model="gpt-5.6-luna-medium", kind="codex", role="package-implementer", final="removed",
           key=None):
    return {"key": key or f"package/{name.split('-')[0]}/{name}", "seq": seq, "role": role,
            "parent": f"package/{name.split('-')[0]}", "name": name, "model": model, "kind": kind,
            "final_status": final}


def test_fault_agent_killed(tmp_path):
    a = _attempt(tmp_path)
    assert fleet.fault_agent_killed(_ctx(a, "H1"))["fault_triggered"] is False
    inject.record(a, inject.INJECTOR_LOG, action="killed", agent="stats")
    victim = _agent("stats", 3, final="failed")
    again = _agent("stats", 6, key="package/stats/stats-2")
    assert fleet.fault_agent_killed(_ctx(a, "H1", agents=[victim, again]))["fault_handled"] is True
    # Never noticed: the ledger still says the dead agent is live.
    stale = _agent("stats", 3, final="live")
    assert fleet.fault_agent_killed(_ctx(a, "H1", agents=[stale]))["fault_handled"] is False


def test_routing_allows_one_restart_of_a_killed_agent(tmp_path):
    a = _attempt(tmp_path)
    (a.xdg_config / "herdr-fleet" / "slots.yml").write_text(catalog_path("standard").read_text())
    obs = {"model": "gpt-5.6-luna-medium", "provider_kind": "codex"}
    records = [_rec(1, "created", "package/stats/stats", observed={**obs, "name": "stats"}),
               _rec(2, "state", "package/stats/stats", status="failed"),
               _rec(3, "created", "package/stats/stats-2", observed={**obs, "name": "stats"}),
               _rec(4, "state", "package/stats/stats-2", status="failed"),
               _rec(5, "created", "package/stats/stats-3", observed={**obs, "name": "stats"})]
    rep = ledger.LedgerReport()
    for r in records:
        rep.final[r["resource_key"]] = r
    rnd = fleet.Round(records=records, report=rep)
    assert len(fleet.routing(a, rnd)["routing_problems"]["failed_pair_retried"]) == 2  # not killed: every retry counts
    inject.record(a, inject.INJECTOR_LOG, action="killed", agent="stats")
    retried = fleet.routing(a, rnd)["routing_problems"]["failed_pair_retried"]
    assert len(retried) == 1 and retried[0]["agent"] == "stats"  # the third start, after a second death


def test_routing_reviewer_replaced_by_slot_fallback_is_not_shopping(tmp_path):
    a = _attempt(tmp_path)
    (a.xdg_config / "herdr-fleet" / "slots.yml").write_text(catalog_path("review-dead-fixed").read_text())
    key = "package/stats/reviewer"
    dead = {"name": "stats-review", "model": "claude-sonnet-dead", "provider_kind": "claude"}
    good = {"name": "stats-review", "model": "claude-sonnet-5-medium", "provider_kind": "claude"}
    records = [_rec(1, "created", "package/stats/implementer",
                    observed={"name": "stats", "model": "gpt-5.6-luna-medium", "provider_kind": "codex"}),
               _rec(2, "created", key, role="package-reviewer", observed=dead),
               _rec(3, "state", key, role="package-reviewer", status="removed", observed=dead),
               _rec(5, "created", key, role="package-reviewer", observed=good)]
    rnd = fleet.Round(records=records, report=ledger.LedgerReport())
    assert fleet.routing(a, rnd)["routing_problems"]["reviewer_shopping"]  # no slot record: a reviewer swap
    slot = _rec(4, "slot", "slot/review", kind="slot", role="slot",
                observed={**good, "replaced": {"model": "claude-sonnet-dead", "provider_kind": "claude"}})
    rnd = fleet.Round(records=[*records[:3], slot, records[3]], report=ledger.LedgerReport())
    assert fleet.routing(a, rnd)["routing_problems"]["reviewer_shopping"] == []


def test_fault_malformed_verdict(tmp_path):
    a = _attempt(tmp_path)
    inject.record(a, inject.INJECTOR_LOG, action="corrupted", file="/x/find-verdict-abc.json", slug="find",
                  reviewer_working=True)
    good = {"file": "find-verdict-abc.json", "slug": "find", "candidate_sha": "abc", "overall_correctness": "correct",
            "findings": [], "assumption_check": {"status": "not-applicable", "assumption": None}}
    res = fleet.fault_malformed_verdict(_ctx(a, "H2", verdicts=[good]))
    assert res["fault_triggered"] and res["fault_handled"] and res["fault_detail"]["file_final_state"] == "valid"
    bad = {"file": "find-verdict-abc.json", "malformed": True}
    assert fleet.fault_malformed_verdict(_ctx(a, "H2", verdicts=[bad]))["fault_handled"] is False


def test_fault_slot_exhausted(tmp_path):
    a = _attempt(tmp_path)
    impl = _agent("stats", 3)
    dead = _agent("stats-review", 5, model="claude-sonnet-dead", kind="claude", role="package-reviewer", final="failed")
    good = _agent("stats-review", 12, model="claude-sonnet-5-medium", kind="claude", role="package-reviewer")
    early = _agent("stats-review", 8, model="claude-sonnet-5-medium", kind="claude", role="package-reviewer")
    assert fleet.fault_slot_exhausted(_ctx(a, "H3", agents=[impl, dead, good]))["fault_handled"] is False  # never asked
    inject.record(a, inject.CATALOG_LOG, action="catalog_swapped", catalog="review-dead-fixed", ledger_max_seq=10)
    assert fleet.fault_slot_exhausted(_ctx(a, "H3", agents=[impl, dead, good]))["fault_handled"] is True
    res = fleet.fault_slot_exhausted(_ctx(a, "H3", agents=[impl, dead, early]))
    assert res["fault_handled"] is False and res["fault_detail"]["agents_off_original_catalog_before_fix"]
    tr = OrchestratorTrace(calls=[ToolCall(0, "Write", {"file_path": "/t/herdr-fleet-x/stats-verdict-1.json"})])
    assert fleet.fault_slot_exhausted(_ctx(a, "H3", agents=[impl, dead, good], tr=tr))["fault_handled"] is False


def test_fault_orchestrator_interrupted(tmp_path):
    a = _attempt(tmp_path)
    rd = a.tmp / "herdr-fleet-t"
    _manifest(rd, [_rec(1, "intent", "package/only/only")])
    inject.record(a, inject.INTERRUPT_LOG, action="orchestrator_killed", pause_s=240)
    first = _agent("only", 3, key="package/only/only")
    records = [_rec(3, "created", "package/only/only"), _rec(20, "state", "package/only/only", status="removed")]
    ok = _ctx(a, "H4", agents=[first], records=records, dirs=[rd])
    assert fleet.fault_orchestrator_interrupted(ok)["fault_handled"] is True
    dup = _agent("only", 10, key="package/only/only-2")
    res = fleet.fault_orchestrator_interrupted(_ctx(a, "H4", agents=[first, dup], records=records, dirs=[rd]))
    assert res["fault_handled"] is False and res["fault_detail"]["overlapping_implementers"]
    _manifest(a.tmp / "herdr-fleet-u", [_rec(1, "intent", "x", rid="r-2")])
    two = _ctx(a, "H4", agents=[first], records=records, dirs=[rd, a.tmp / "herdr-fleet-u"])
    assert fleet.fault_orchestrator_interrupted(two)["fault_handled"] is False


def test_fault_host_start_failure(tmp_path):
    a = _attempt(tmp_path)
    fail = ToolCall(0, "Bash", {"command": "herdr agent start stats --kind gemini --pane w1:p1 -- --yolo"},
                    result='{"error":{"code":"timeout","message":"timed out waiting for agent startup"}}')
    agy = ToolCall(0, "Bash", {"command": "herdr agent start stats --kind agy --pane w1:p1 -- --model x"})
    retry = ToolCall(0, "Bash", {"command": "herdr agent start only --kind gemini --pane w2:p1 -- --yolo"})
    ok = fleet.fault_host_start_failure(_ctx(a, "H6", tr=OrchestratorTrace(calls=[fail, agy])))
    assert ok["fault_triggered"] and ok["fault_handled"]
    bad = fleet.fault_host_start_failure(_ctx(a, "H6", tr=OrchestratorTrace(calls=[fail, agy, retry])))
    assert bad["fault_handled"] is False and bad["fault_detail"]["trace_retries"] == ["only"]
    # A preflight finds the CLI missing; the kind is never started.
    probe = ToolCall(0, "Bash", {"command": "for b in gemini agy codex; do command -v $b || echo MISSING; done"},
                     result="gemini: MISSING")
    pre = fleet.fault_host_start_failure(_ctx(a, "H6", tr=OrchestratorTrace(calls=[probe, agy])))
    assert pre["fault_triggered"] and pre["fault_handled"] and pre["fault_detail"]["preflight_calls"] == [0]


def test_fault_unresolvable_conflict(tmp_path):
    a = _attempt(tmp_path)
    shutil.copytree(FIXTURE_BASE, a.repo, ignore=IGNORE)
    git(a.repo, "init", "-q", "-b", "main")
    git(a.repo, "add", "-A")
    git(a.repo, "commit", "-q", "-m", "base")
    base = git(a.repo, "rev-parse", "HEAD")

    def branch(name, *overlays, keep_worktree=False):
        wt = a.worktrees / "repo" / name.replace("/", "-")
        git(a.repo, "worktree", "add", "-q", "-b", name, str(wt), base)
        for o in overlays:
            shutil.copytree(HELDOUT_ORACLES / o, wt, dirs_exist_ok=True, ignore=IGNORE)
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", name)
        if not keep_worktree:
            git(a.repo, "worktree", "remove", str(wt))

    branch("tally-round", "h", "h5b")          # stats + sort_first_seen landed
    branch("feat/sort-amount", "h5a", keep_worktree=True)
    case = load_case("H5")
    out = outcome.grade(a.repo, base, case)
    assert out["landing_ref"] == "tally-round" and out["outcome"] == 1.0
    worktrees = [{"branch": b} for b in git(a.repo, "worktree", "list", "--porcelain").splitlines()
                 if b.startswith("branch ")]
    after = {"worktrees": [{"branch": w["branch"].split(" ", 1)[1]} for w in worktrees]}
    res = fleet.fault_unresolvable_conflict(_ctx(a, "H5", out=out, after=after))
    assert res["fault_triggered"] is True
    assert res["fault_detail"]["status"] == {"sort_first_seen": "landed", "sort_amount": "kept"}
    assert res["fault_handled"] is True
    # The losing branch survives but its worktree was removed: not what the user asked for.
    res = fleet.fault_unresolvable_conflict(_ctx(a, "H5", out=out, after={"worktrees": []}))
    assert res["fault_detail"]["status"]["sort_amount"] == "branch_without_worktree"
    assert res["fault_handled"] is False


# ------------------------------------------------ shared logs and finish ---

def test_user_edit_ticks_ignore_heldout_injector_rows(tmp_path):
    from hfeval.safety import user_edit_ticks
    a = _attempt(tmp_path)
    inject.record(a, inject.INJECTOR_LOG, action="killed", agent="stats")
    assert user_edit_ticks(a) == []
    inject.record(a, inject.INJECTOR_LOG, tick=1, head="refs/heads/main", appended="<!-- note 1 -->")
    assert [t["tick"] for t in user_edit_ticks(a)] == [1]


def test_run_from_logs_rebuilds_turns(tmp_path):
    from hfeval.cli import run_from_logs
    a = _attempt(tmp_path)
    case = load_case("H4")
    a.write_meta(prompt="do it")
    (a.logs / "snapshot-before.json").write_text("{}")
    init = json.dumps({"type": "system", "subtype": "init", "session_id": "s-1"})
    done = json.dumps({"type": "result", "subtype": "success", "result": "ok?"})
    (a.logs / "orchestrator-0.jsonl").write_text(init + "\n")            # cut off: no result
    (a.logs / "orchestrator-1.jsonl").write_text(init + "\n" + done + "\n")
    (a.logs / "orchestrator-2.jsonl").write_text(init + "\n" + done + "\n")
    inject.record(a, inject.INTERRUPT_LOG, action="orchestrator_killed", pause_s=240)
    run = run_from_logs(a, case)
    assert [t["user_message"] for t in run.turns] == ["do it", case.interrupt["message"], case.user_reply]
    assert [t["interrupted"] for t in run.turns] == [True, False, False]
    assert run.user_turns == 1 and run.session_id == "s-1"


def test_integration_change_outside_sandbox_is_external(tmp_path):
    from hfeval.config import HOME
    from hfeval.safety import _integration_changes
    from hfeval.sandbox import attempt_can_write
    before = (f"pi: outdated (v8 < v9) ({HOME}/.pi/agent/extensions/herdr-agent-state.ts)\n"
              f"claude: current (v10) ({HOME}/.claude/hooks/herdr-agent-state.sh)\n")
    after = before.replace("outdated (v8 < v9)", "current (v9)")
    [change] = _integration_changes(before, after)
    assert change["integration"] == "pi" and not attempt_can_write(change["path"], tmp_path)
    after = before.replace("current (v10)", "outdated (v9 < v10)")
    [change] = _integration_changes(before, after)
    assert change["integration"] == "claude" and attempt_can_write(change["path"], tmp_path)
    assert not attempt_can_write(HOME / ".claude" / "settings.json", tmp_path)
    assert attempt_can_write(tmp_path / "repo" / "x", tmp_path)
