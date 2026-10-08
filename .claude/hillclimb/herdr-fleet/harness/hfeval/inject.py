"""Held-out fault injectors. Each acts at most once and appends what it did
to a JSONL record under `<attempt>/logs/`, which the fault graders read.

  kill_agent       SIGKILL a package implementer's process group once it
                   has been `working` for `min_working_s` (H1)
  corrupt_verdict  truncate the first complete verdict file while its
                   reviewer is still `working` (H2)
  interrupt        SIGKILL the orchestrator once a worktree has a commit and
                   an agent is working, so the harness can resume it (H4)
  swap_catalog     replace slots.yml before the first user reply (H3)

Only processes descending from the attempt's own herdr server are ever
signalled.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path

from hfeval.config import catalog_path
from hfeval.fixture import Attempt, git
from hfeval.herdr import Session

INJECTOR_LOG = "injector.jsonl"
INTERRUPT_LOG = "interrupt.jsonl"
CATALOG_LOG = "reply_catalog.jsonl"
# Agents that are not package implementers (skill naming, step 3).
AUX_AGENT = re.compile(r"-(review|adjudicate|merge|merge-review|suite-fix|suite-review|triage)$|-scout-\d+$")


def record(attempt: Attempt, log: str, **fields) -> dict:
    row = {"t": time.time(), **fields}
    with open(attempt.logs / log, "a") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


def read_log(attempt: Attempt, log: str) -> list[dict]:
    path = attempt.logs / log
    rows = []
    for line in path.read_text().splitlines() if path.exists() else []:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _agents(session: Session) -> list[dict]:
    return session.call("agent", "list").get("result", {}).get("agents", [])


def descends_from(pid: int, ancestor: int) -> bool:
    ps = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True).stdout
    parent = {int(a): int(b) for a, b in (line.split() for line in ps.splitlines() if line.strip())}
    seen = set()
    while pid and pid not in seen:
        if pid == ancestor:
            return True
        seen.add(pid)
        pid = parent.get(pid, 0)
    return False


def kill_agent(attempt: Attempt, session: Session, spec: dict, stop: threading.Event) -> None:
    min_working = spec.get("min_working_s", 75)
    since: dict[str, float] = {}
    while not stop.wait(spec.get("poll_s", 5)):
        now = time.time()
        for a in _agents(session):
            name = a.get("name") or ""
            if AUX_AGENT.search(name) or a.get("agent_status") != "working":
                since.pop(name, None)
                continue
            since.setdefault(name, now)
            if now - since[name] < min_working:
                continue
            info = session.call("pane", "process-info", "--pane", a.get("pane_id", "")).get("result", {}) \
                .get("process_info", {})
            pgid, shell = info.get("foreground_process_group_id"), info.get("shell_pid")
            procs = [p.get("cmdline") for p in info.get("foreground_processes", [])]
            server = session.proc.pid if session.proc else None
            if not pgid or pgid == shell or not server or not descends_from(pgid, server):
                record(attempt, INJECTOR_LOG, action="skipped", agent=name, pane=a.get("pane_id"), pgid=pgid,
                       shell_pid=shell, processes=procs)
                since.pop(name, None)
                continue
            os.killpg(pgid, signal.SIGKILL)
            record(attempt, INJECTOR_LOG, action="killed", agent=name, pane=a.get("pane_id"), pgid=pgid,
                   processes=procs, working_for_s=round(now - since[name], 1))
            return


def corrupt_verdict(attempt: Attempt, session: Session, spec: dict, stop: threading.Event) -> None:
    sizes: dict[Path, int] = {}
    while not stop.wait(spec.get("poll_s", 0.1)):
        found = [*attempt.tmp.glob("herdr-fleet-*/*verdict*.json"), *attempt.state.glob("herdr-fleet/*/*verdict*.json")]
        for f in sorted(found):
            try:
                data = f.read_bytes()
            except OSError:
                continue
            prev, sizes[f] = sizes.get(f), len(data)
            if not data or prev != len(data):
                continue  # empty or still growing
            try:
                json.loads(data)
            except ValueError:
                continue  # not complete yet
            slug = f.name.split("-verdict-")[0]
            statuses = {a.get("name"): a.get("agent_status") for a in _agents(session)
                        if (a.get("name") or "").startswith(slug) and AUX_AGENT.search(a.get("name") or "")}
            f.write_bytes(data[: len(data) // 2])
            record(attempt, INJECTOR_LOG, action="corrupted", file=str(f), slug=slug,
                   original_sha256=hashlib.sha256(data).hexdigest(), original_bytes=len(data),
                   kept_bytes=len(data) // 2, reviewer_statuses=statuses,
                   reviewer_working=any(s == "working" for s in statuses.values()))
            return


def interrupt_when_ready(attempt: Attempt, session: Session, proc: subprocess.Popen, spec: dict,
                         fired: dict) -> None:
    """Kill the orchestrator mid-round, as a usage limit would cut it off."""
    base = attempt.meta()["base_sha"]
    while proc.poll() is None:
        time.sleep(spec.get("poll_s", 10))
        committed = [str(wt) for wt in attempt.worktrees.glob("*/*") if wt.is_dir()
                     and git(wt, "rev-list", "--count", f"{base}..HEAD", check=False) not in ("", "0")]
        working = [a.get("name") for a in _agents(session) if a.get("agent_status") == "working"]
        if committed and working and proc.poll() is None:
            # Recorded before the kill, so the turn loop never sees the exit without it.
            fired.update(record(attempt, INTERRUPT_LOG, action="orchestrator_killed", worktrees_with_commits=committed,
                                working_agents=working, pause_s=spec.get("pause_s", 240)))
            os.killpg(proc.pid, signal.SIGKILL)
            return


def swap_catalog(attempt: Attempt, name: str) -> dict:
    """Write the user's fixed catalog; remember how far the ledger had got."""
    from hfeval.fleet import find_round

    rnd = find_round(attempt)
    seqs = [r.get("seq") for r in rnd.records if isinstance(r.get("seq"), int)]
    (attempt.xdg_config / "herdr-fleet" / "slots.yml").write_text(catalog_path(name).read_text())
    return record(attempt, CATALOG_LOG, action="catalog_swapped", catalog=name,
                  ledger_max_seq=max(seqs) if seqs else None)


INJECTORS = {"kill_agent": kill_agent, "corrupt_verdict": corrupt_verdict}
