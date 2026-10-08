"""Run the orchestrator (`claude -p`) for one attempt, with a scripted user.

The orchestrator runs sandboxed, outside herdr (the skill supports this:
it reaches the server through `HERDR_SOCKET_PATH` and creates its own
round workspace). When a turn ends while the round is still open (live
agents, a round directory without an archive, or a closing question) the
simulated user answers with the case's `user_reply` via `--resume`, up to
`max_user_turns`. A case with `interrupt` has its first turn killed
mid-round and resumed after a pause, without counting as a user turn; a
case with `reply_catalog` has its catalog fixed before the first reply.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from hfeval import inject
from hfeval.config import Case
from hfeval.fixture import Attempt, git
from hfeval.herdr import Session, base_env


@dataclass
class OrchestratorRun:
    turns: list[dict] = field(default_factory=list)  # one per `claude -p` invocation
    user_turns: int = 0
    timed_out: bool = False
    budget_exhausted: bool = False
    session_id: str | None = None
    interrupts: list[dict] = field(default_factory=list)
    started: float = 0.0
    ended: float = 0.0


def orchestrator_env(attempt: Attempt, session: Session) -> dict[str, str]:
    return {
        **base_env(),
        "TMPDIR": f"{attempt.tmp}/",
        "XDG_STATE_HOME": str(attempt.state),
        "XDG_CONFIG_HOME": str(attempt.xdg_config),
        "HERDR_SOCKET_PATH": str(session.socket),
        "CODEX_HOME": str(attempt.codex_home),
    }


def _round_closed(d: Path) -> bool:
    m = d / "manifest.jsonl"
    if not m.exists():
        return True
    for line in m.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("resource_key") == "round/dir" and r.get("event") == "state":
            return True
    # The previous layout archived a round only at its very end.
    return not (d / "state.json").exists()


def _round_open(attempt: Attempt, session: Session, with_skill: bool, final_text: str) -> bool:
    agents = session.call("agent", "list").get("result", {}).get("agents", [])
    if agents:
        return True
    asks = "?" in final_text.strip().split("\n\n")[-1] if final_text.strip() else False
    if not with_skill:
        return asks
    round_dirs = list(attempt.tmp.glob("herdr-fleet-*"))
    archives = list((attempt.state / "herdr-fleet").glob("*")) if (attempt.state / "herdr-fleet").exists() else []
    seeded = set(attempt.meta().get("seeds", {}).get("round_dirs", []))
    live_round_dirs = [d for d in round_dirs if str(d) not in seeded]
    # A round directory kept under the state root is closed once its ledger
    # records a disposition for round/dir; until then it is the live round.
    open_in_state = [d for d in archives if not _round_closed(d)]
    live_round_dirs += open_in_state
    if archives and not open_in_state:
        return False
    return bool(live_round_dirs) or asks


def run(
    attempt: Attempt, session: Session, case: Case, prompt: str, *, with_skill: bool,
    wall_clock_s: int, budget_usd: float, model: str | None,
) -> OrchestratorRun:
    out = OrchestratorRun(started=time.time())
    stop = threading.Event()
    injectors = [threading.Thread(target=_inject, args=(attempt, session, spec, stop), daemon=True)
                 for spec in case.injectors]
    for t in injectors:
        t.start()
    profile = attempt.logs / "sandbox.sb"
    deadline = out.started + wall_clock_s
    spent = 0.0
    message = prompt
    turn = 0
    try:
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                out.timed_out = True
                break
            cmd = ["sandbox-exec", "-f", str(profile), "claude", "-p",
                   "--output-format", "stream-json", "--verbose",
                   "--permission-mode", "bypassPermissions",
                   "--max-budget-usd", f"{max(budget_usd - spent, 0.5):.2f}"]
            if model:
                cmd += ["--model", model]
            if with_skill:
                cmd += ["--plugin-dir", str(attempt.plugin)]
            if out.session_id:
                cmd += ["--resume", out.session_id]
            log = attempt.logs / f"orchestrator-{turn}.jsonl"
            with open(log, "w") as fh:
                proc = subprocess.Popen(
                    cmd, cwd=attempt.repo, env=orchestrator_env(attempt, session),
                    stdin=subprocess.PIPE, stdout=fh, stderr=open(attempt.logs / f"orchestrator-{turn}.err", "w"),
                    text=True, start_new_session=True,
                )
                proc.stdin.write(message)
                proc.stdin.close()
                fired: dict = {}
                watcher = None
                if case.interrupt and not out.interrupts:
                    watcher = threading.Thread(target=inject.interrupt_when_ready,
                                               args=(attempt, session, proc, case.interrupt, fired), daemon=True)
                    watcher.start()
                try:
                    proc.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    time.sleep(5)
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                    out.timed_out = True
                if watcher:
                    watcher.join(timeout=30)
            events = _read_jsonl(log)
            result = next((e for e in reversed(events) if e.get("type") == "result"), {})
            init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), {})
            out.session_id = out.session_id or init.get("session_id") or result.get("session_id")
            spent += float(result.get("total_cost_usd") or 0.0)
            out.turns.append({"turn": turn, "user_message": message, "log": log.name, "exit": proc.returncode,
                              "result_subtype": result.get("subtype"), "cost_usd": result.get("total_cost_usd"),
                              "duration_ms": result.get("duration_ms"), "interrupted": bool(fired)})
            turn += 1
            if out.timed_out:
                break
            if result.get("subtype") == "error_max_budget_usd" or spent >= budget_usd:
                out.budget_exhausted = True
                break
            if fired and out.session_id:
                out.interrupts.append(fired)
                time.sleep(min(fired["pause_s"], max(deadline - time.time(), 0)))
                message = case.interrupt["message"]
                continue
            if not out.session_id or not _round_open(attempt, session, with_skill, result.get("result") or ""):
                break
            if out.user_turns == case.max_user_turns:
                break
            if case.reply_catalog and out.user_turns == 0:
                inject.swap_catalog(attempt, case.reply_catalog)
            message = case.user_reply
            out.user_turns += 1
    finally:
        stop.set()
        for t in injectors:
            t.join(timeout=5)
        out.ended = time.time()
    return out


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text().splitlines() if path.exists() else []:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _inject(attempt: Attempt, session: Session, spec: dict, stop: threading.Event) -> None:
    if spec.get("type") in inject.INJECTORS:
        inject.INJECTORS[spec["type"]](attempt, session, spec, stop)
        return
    # R2: the user keeps editing a file in the main checkout mid-round.
    if spec.get("type") != "user_edit":
        return
    record = attempt.logs / "injector.jsonl"
    target = attempt.repo / spec["path"]
    while not stop.is_set() and spec.get("start_when") == "first_worktree":
        # herdr lays worktrees out as <worktrees>/<repo-name>/<branch-slug>.
        if any(p.is_dir() for p in attempt.worktrees.glob("*/*")):
            break
        stop.wait(5)
    n = 0
    while not stop.is_set():
        n += 1
        head = git(attempt.repo, "symbolic-ref", "-q", "HEAD", check=False) or "DETACHED"
        line = f"\n<!-- user draft note {n} -->\n"
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(line)
        with open(record, "a") as fh:
            fh.write(json.dumps({"t": time.time(), "tick": n, "head": head, "appended": line.strip(),
                                 "status": git(attempt.repo, "status", "--porcelain", check=False)}) + "\n")
        stop.wait(spec.get("interval_s", 90))
