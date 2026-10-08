"""Validate a herdr-fleet round ledger (manifest.jsonl) and its archive.

Offline checks need only the manifest. `live_consistency` additionally
compares final recorded dispositions against the attempt's real git and
herdr state, so it is only available for end-to-end runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

EVENTS = {"intent", "created", "state", "slot"}
KINDS = {"worktree", "workspace", "tab", "pane", "agent", "branch", "dir", "slot"}
ROLES = {
    "package-container", "package-implementer", "package-reviewer", "check-pane", "review-pane",
    "scout-container", "scout", "merge-container", "merge-implementer", "merge-implementer-pane",
    "merge-reviewer", "merge-reviewer-pane", "merge-check-pane", "merge-worktree", "package-branch",
    "round-dir", "round-workspace", "merge-target", "round-archive", "container-root-pane", "slot",
}
POLICIES = {"remove-when-merged", "close-aux", "close-container", "delete-on-success", "report-only"}
STATUSES = {"planned", "live", "removed", "retained", "failed"}
TERMINAL = {"removed", "retained", "failed"}
REQUIRED = ["schema_version", "round_id", "round_slug", "seq", "event", "resource_key", "kind", "role",
            "parent_key", "cleanup_policy", "selector", "observed", "status", "detail"]


@dataclass
class LedgerReport:
    records: int = 0
    corrupt_lines: list[int] = field(default_factory=list)
    seq_problems: list[str] = field(default_factory=list)
    round_ids: set[str] = field(default_factory=set)
    schema_problems: list[str] = field(default_factory=list)
    created_without_intent: list[str] = field(default_factory=list)
    state_on_uncreated: list[str] = field(default_factory=list)
    no_terminal: list[str] = field(default_factory=list)
    dangling_intents: list[str] = field(default_factory=list)
    duplicate_terminal: list[str] = field(default_factory=list)
    archive_problems: list[str] = field(default_factory=list)
    live_mismatches: list[str] = field(default_factory=list)
    unrecorded_live: list[str] = field(default_factory=list)
    final: dict[str, dict] = field(default_factory=dict)  # resource_key -> last record

    def checks(self, with_live: bool) -> dict[str, bool]:
        out = {
            "parse": not self.corrupt_lines,
            "seq_monotonic": not self.seq_problems,
            "single_round_id": len(self.round_ids) == 1,
            "schema": not self.schema_problems,
            "write_ahead": not self.created_without_intent,
            "no_orphan_state": not self.state_on_uncreated,
            "terminal_dispositions": not self.no_terminal and not self.dangling_intents
            and not self.duplicate_terminal,
            "archive": not self.archive_problems,
        }
        if with_live:
            out["live_consistency"] = not self.live_mismatches and not self.unrecorded_live
        return out

    def score(self, with_live: bool) -> float:
        c = self.checks(with_live)
        return sum(c.values()) / len(c)

    def to_dict(self, with_live: bool) -> dict:
        d = {k: (sorted(v) if isinstance(v, set) else v) for k, v in self.__dict__.items() if k != "final"}
        d["checks"] = self.checks(with_live)
        d["score"] = round(self.score(with_live), 3)
        return d


def load(path: Path) -> tuple[list[dict], list[int]]:
    """Parse JSONL tolerantly; a record broken across lines counts once, at its first line."""
    records, corrupt = [], []
    lines = path.read_text(errors="replace").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            corrupt.append(i)
            # Swallow continuation lines of the same broken record.
            while i < len(lines) and not lines[i].lstrip().startswith('{"schema_version"'):
                i += 1
    return records, corrupt


def validate(round_dir_or_archive: Path, archive_root: Path | None = None) -> LedgerReport:
    manifest = round_dir_or_archive / "manifest.jsonl"
    rep = LedgerReport()
    if not manifest.exists():
        rep.corrupt_lines.append(0)
        rep.archive_problems.append("no manifest.jsonl")
        return rep
    records, rep.corrupt_lines = load(manifest)
    rep.records = len(records)

    seen_seq: set[int] = set()
    prev = 0
    for r in records:
        seq = r.get("seq")
        if not isinstance(seq, int):
            rep.seq_problems.append(f"non-integer seq {seq!r}")
            continue
        if seq in seen_seq:
            rep.seq_problems.append(f"duplicate seq {seq}")
        elif seq != prev + 1:
            rep.seq_problems.append(f"seq {seq} after {prev}")
        seen_seq.add(seq)
        prev = max(prev, seq)
        rep.round_ids.add(str(r.get("round_id")))

        missing = [k for k in REQUIRED if k not in r]
        bad = []
        if r.get("schema_version") != 3:
            bad.append(f"schema_version={r.get('schema_version')}")
        for key, allowed in (("event", EVENTS), ("kind", KINDS), ("role", ROLES),
                             ("cleanup_policy", POLICIES), ("status", STATUSES)):
            if key in r and r[key] not in allowed:
                bad.append(f"{key}={r[key]}")
        if missing or bad:
            rep.schema_problems.append(f"seq {seq}: " + ", ".join([f"missing {m}" for m in missing] + bad))

    intents: set[str] = set()
    created: set[str] = set()
    for r in records:
        key, ev = r.get("resource_key"), r.get("event")
        if ev == "intent":
            intents.add(key)
        elif ev == "created":
            if key not in intents and r.get("role") != "round-dir":
                rep.created_without_intent.append(f"seq {r.get('seq')} {key}")
            created.add(key)
        elif ev == "state" and key not in created and r.get("kind") != "slot":
            legit_failed = r.get("status") == "failed" and key in intents
            if not legit_failed:
                rep.state_on_uncreated.append(f"seq {r.get('seq')} {key}")
        if ev == "state" and key in rep.final and rep.final[key].get("status") in TERMINAL \
                and r.get("status") == rep.final[key].get("status"):
            rep.duplicate_terminal.append(f"seq {r.get('seq')} {key} {r.get('status')} again")
        if ev in ("created", "state") and key:
            rep.final[key] = r

    last_event: dict[str, str] = {}
    for r in records:
        if r.get("resource_key"):
            last_event[r["resource_key"]] = r.get("event")
    for key in sorted(k for k, ev in last_event.items() if ev == "intent"):
        rep.dangling_intents.append(key)

    for key in sorted(created):
        last = rep.final.get(key, {})
        if last.get("role") in ("round-dir", "slot") or last.get("kind") == "slot":
            continue
        if last.get("status") not in TERMINAL:
            rep.no_terminal.append(f"{key} ({last.get('status')})")

    _check_archive(rep, records, round_dir_or_archive, archive_root)
    return rep


def _check_archive(rep: LedgerReport, records: list[dict], here: Path, archive_root: Path | None) -> None:
    arch = [r for r in records if r.get("resource_key") == "round/archive" or r.get("role") == "round-archive"]
    # A round directory created under the archive root is its own archive.
    in_place = archive_root is not None and here.resolve().parent == archive_root.resolve()
    if not in_place and not any(r.get("event") == "created" for r in arch):
        rep.archive_problems.append("no created event for round/archive")
    if archive_root is None:
        return
    rid = next(iter(rep.round_ids), "")
    matches = [p for p in archive_root.glob("*") if p.is_dir() and p.name.endswith(rid)] if archive_root.exists() else []
    if not matches:
        rep.archive_problems.append(f"no archive dir ending in {rid} under {archive_root}")
        return
    archived = matches[0] / "manifest.jsonl"
    if not archived.exists():
        rep.archive_problems.append("archive has no manifest.jsonl")
        return
    lines = [l for l in archived.read_text().splitlines() if l.strip()]
    try:
        if json.loads(lines[-1]).get("round_id") != rid:
            rep.archive_problems.append("archived manifest last line has a different round_id")
    except (IndexError, json.JSONDecodeError):
        rep.archive_problems.append("archived manifest last line unparseable")
    if here.resolve() != matches[0].resolve() and here.exists():
        for f in here.rglob("*"):
            twin = matches[0] / f.relative_to(here)
            if f.is_file() and (not twin.exists() or twin.read_bytes() != f.read_bytes()):
                rep.archive_problems.append(f"archive differs from round dir at {f.relative_to(here)}")
                break


def check_live(rep: LedgerReport, *, branches: dict[str, str], worktree_paths: set[str],
               herdr_snapshot: dict, preexisting: dict) -> None:
    """Compare the ledger's final dispositions with reality after the round."""
    agents = {a.get("name") for a in herdr_snapshot.get("agents", {}).get("agents", []) if a.get("name")}
    workspaces = {w.get("workspace_id") for w in herdr_snapshot.get("workspaces", [])}
    for key, last in rep.final.items():
        kind, status = last.get("kind"), last.get("status")
        obs = {**(last.get("selector") or {}), **(last.get("observed") or {})}
        alive = None
        if kind == "branch" and obs.get("branch"):
            alive = f"refs/heads/{obs['branch']}" in branches
        elif kind == "worktree" and obs.get("path"):
            alive = obs["path"] in worktree_paths or Path(obs["path"]).exists()
        elif kind == "agent" and obs.get("name"):
            alive = obs["name"] in agents
        elif kind == "workspace" and obs.get("workspace_id"):
            alive = obs["workspace_id"] in workspaces
        if alive is None:
            continue
        if status == "removed" and alive:
            rep.live_mismatches.append(f"{key}: recorded removed but still live")
        if status in ("live", "retained") and not alive:
            rep.live_mismatches.append(f"{key}: recorded {status} but gone")
    recorded_agents = {((r.get("observed") or {}).get("name") or (r.get("selector") or {}).get("name"))
                       for r in rep.final.values() if r.get("kind") == "agent"}
    for name in agents - recorded_agents - set(preexisting.get("agents", [])):
        rep.unrecorded_live.append(f"agent {name}")
    recorded_ws = {(r.get("observed") or {}).get("workspace_id") for r in rep.final.values()}
    # `herdr worktree create` also opens a workspace for the main checkout;
    # that is herdr's side effect, reported separately by the grader.
    main_ws = {w.get("workspace_id") for w in herdr_snapshot.get("workspaces", [])
               if (w.get("worktree") or {}).get("is_linked_worktree") is False}
    for ws in workspaces - recorded_ws - main_ws - set(preexisting.get("workspaces", [])):
        rep.unrecorded_live.append(f"workspace {ws}")
