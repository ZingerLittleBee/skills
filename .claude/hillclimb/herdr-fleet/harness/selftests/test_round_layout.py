"""Graders against the fleet.py layout: the round directory lives under the
state root from the start and is closed by a ledger disposition."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from hfeval import fleet, inject, ledger, orchestrate
from selftests.test_heldout import StubSession, _attempt


def _rec(seq, event, key, kind, role, status, **kw):
    return {"schema_version": 3, "round_id": "r-1", "round_slug": "r", "seq": seq, "event": event,
            "resource_key": key, "kind": kind, "role": role, "parent_key": kw.get("parent"),
            "cleanup_policy": kw.get("policy", "report-only"), "selector": {}, "observed": kw.get("observed", {}),
            "status": status, "detail": None}


def _round_dir(a, closed: bool) -> Path:
    rd = a.state / "herdr-fleet" / "r-r-1"
    rd.mkdir(parents=True)
    recs = [_rec(1, "created", "round/dir", "dir", "round-dir", "live", observed={"path": str(rd)})]
    if closed:
        recs.append(_rec(2, "state", "round/dir", "dir", "round-dir", "retained"))
    (rd / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in recs))
    (rd / "state.json").write_text("{}")
    return rd


def test_round_dir_under_state_root_is_its_own_archive(tmp_path):
    a = _attempt(tmp_path)
    rd = _round_dir(a, closed=True)
    rep = ledger.validate(rd, archive_root=a.state / "herdr-fleet")
    assert rep.archive_problems == []
    elsewhere = a.tmp / "herdr-fleet-r"
    elsewhere.mkdir()
    (elsewhere / "manifest.jsonl").write_text((rd / "manifest.jsonl").read_text())
    assert "no created event for round/archive" in ledger.validate(elsewhere, archive_root=a.state / "herdr-fleet").archive_problems


def test_round_stays_open_until_round_dir_disposition(tmp_path):
    a = _attempt(tmp_path)
    rd = _round_dir(a, closed=False)
    assert not orchestrate._round_closed(rd)
    with open(rd / "manifest.jsonl", "a") as fh:
        fh.write(json.dumps(_rec(2, "state", "round/dir", "dir", "round-dir", "retained")) + "\n")
    assert orchestrate._round_closed(rd)


def test_corrupt_verdict_finds_verdicts_under_state_root(tmp_path):
    a = _attempt(tmp_path)
    rd = _round_dir(a, closed=False)
    session = StubSession([{"name": "stats-review", "agent_status": "working"}])
    th = threading.Thread(target=inject.corrupt_verdict, args=(a, session, {}, threading.Event()), daemon=True)
    th.start()
    body = json.dumps({"candidate_sha": "abc", "overall_correctness": "correct", "findings": []})
    (rd / "stats-verdict-abc.json").write_text(body)
    th.join(timeout=5)
    assert (rd / "stats-verdict-abc.json").read_text() == body[: len(body) // 2]


def test_merge_worktree_agents_group_by_pair():
    def g(name):
        return fleet._group({"parent": "round/merge-worktree", "name": name})
    assert g("stats-merge") == g("stats-merge-review") == "merge:stats"
    assert g("r-suite-fix") == g("r-suite-review") == "merge:r"
    assert g("stats-merge") != g("other-merge")
