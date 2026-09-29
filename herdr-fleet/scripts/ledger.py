#!/usr/bin/env python3
"""Append one event to a herdr-fleet round manifest.

The manifest is the round's append-only JSONL ledger (SKILL.md step 3).
This script is its only writer: it locks the file, assigns the next
`seq`, fills `schema_version`, `round_id` and `round_slug` from the
first record, validates every enum, and lets `created`, `state` and
`slot` events inherit what earlier events of the same resource already
said. It prints the appended record's seq and key, or exits non-zero
with the reason and appends nothing.

    ledger.py <manifest> <event> <resource_key> [options]

Options:
    --kind K --role R --parent KEY --policy P --status S --detail TEXT
    --selector k=v    repeatable; dotted keys nest (replaced.model=x)
    --observed k=v    repeatable; dotted keys nest
    --round-id ID --round-slug SLUG    first record only

Standard library only; runs on Python 3.9 and later.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys

SCHEMA_VERSION = 3
EVENTS = ("intent", "created", "state", "slot")
KINDS = ("worktree", "workspace", "tab", "pane", "agent", "branch", "dir", "slot")
ROLES = (
    "package-container", "package-implementer", "package-reviewer", "check-pane",
    "review-pane", "scout-container", "scout", "merge-container", "merge-implementer",
    "merge-implementer-pane", "merge-reviewer", "merge-reviewer-pane", "merge-check-pane",
    "package-branch", "round-dir", "round-workspace", "merge-target", "round-archive",
    "container-root-pane", "slot",
)
POLICIES = ("remove-when-merged", "close-aux", "close-container", "delete-on-success", "report-only")
STATUSES = ("planned", "live", "removed", "retained", "failed")
TERMINAL = ("removed", "failed")
SLOT_OBSERVED = ("model", "provider_kind", "args")


class LedgerError(Exception):
    pass


def pairs(items: list[str] | None, flag: str) -> dict:
    """`a.b=v` pairs to a nested dict; values stay strings."""
    out: dict = {}
    for item in items or []:
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise LedgerError(f"{flag} takes key=value, got {item!r}")
        node = out
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise LedgerError(f"{flag} {key!r} nests under a plain value")
        node[parts[-1]] = value
    return out


def merged(base: dict, extra: dict) -> dict:
    out = dict(base)
    for key, value in extra.items():
        out[key] = merged(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def read_records(fh) -> list[dict]:
    fh.seek(0)
    records = []
    for n, line in enumerate(fh.read().splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise LedgerError(f"line {n} is not JSON ({exc}); repair the manifest before appending") from exc
    return records


def choose(name: str, value, allowed: tuple) -> None:
    if value not in allowed:
        raise LedgerError(f"--{name} must be one of {', '.join(allowed)}; got {value!r}")


def build(records: list[dict], a: argparse.Namespace) -> dict:
    key = a.resource_key
    if not key or any(c.isspace() for c in key):
        raise LedgerError(f"resource_key must be non-empty with no spaces; got {key!r}")
    history = [r for r in records if r.get("resource_key") == key]
    prior = history[-1] if history else {}
    observed = pairs(a.observed, "--observed")
    selector = pairs(a.selector, "--selector")

    if not records:
        if a.event != "created" or a.kind != "dir" or a.role != "round-dir":
            raise LedgerError("the first record is `created` for the round directory (--kind dir --role round-dir)")
        if not (a.round_id and a.round_slug):
            raise LedgerError("the first record needs --round-id and --round-slug")
        round_id, round_slug = a.round_id, a.round_slug
    else:
        round_id, round_slug = records[0].get("round_id"), records[0].get("round_slug")
        for flag, given, have in (("--round-id", a.round_id, round_id), ("--round-slug", a.round_slug, round_slug)):
            if given and given != have:
                raise LedgerError(f"{flag} {given!r} differs from this manifest's {have!r}")

    rec = {
        "kind": a.kind or prior.get("kind"),
        "role": a.role or prior.get("role"),
        "parent_key": a.parent if a.parent is not None else prior.get("parent_key"),
        "cleanup_policy": a.policy or prior.get("cleanup_policy"),
        "selector": merged(prior.get("selector") or {}, selector),
        "observed": {},
        "status": a.status,
    }

    # A key may be reused for a replacement (a restart or a slot fallback in
    # the same pane) once its previous generation reached a terminal status.
    if a.event == "intent":
        if prior and prior.get("status") not in TERMINAL:
            raise LedgerError(
                f"{key} is still {prior.get('status')} (seq {prior.get('seq')}); append its terminal state "
                f"(removed or failed) before a replacement's intent")
        if observed:
            raise LedgerError("an intent carries no --observed; record the real ids on `created`")
        rec["status"] = a.status or "planned"
        if rec["status"] != "planned":
            raise LedgerError("an intent's status is planned")
    elif a.event == "created":
        if records and prior.get("event") != "intent":
            latest = f"its latest event is {prior['event']} {prior.get('status')}" if prior else "it has no events"
            raise LedgerError(
                f"no pending intent for {key} ({latest}). Record a change to a created resource as `state`. "
                f"Every resource but the round directory is write-ahead: if this one already exists "
                f"unrecorded, append its intent now with --detail naming the late write, then created")
        if not observed:
            raise LedgerError("created needs --observed with the real ids from the create response")
        rec["observed"] = observed
        rec["status"] = a.status or "live"
    elif a.event == "state":
        if not history:
            raise LedgerError(f"no earlier event for {key}; a state records a disposition of a recorded resource")
        if not a.status:
            raise LedgerError("a state event needs --status")
        rec["observed"] = merged(prior.get("observed") or {}, observed)
    else:  # slot
        if not key.startswith("slot/"):
            raise LedgerError("a slot event's resource_key is slot/<name>")
        rec.update(kind="slot", role="slot", parent_key=None, cleanup_policy="report-only",
                   status=a.status or "live")
        rec["observed"] = observed
        missing = [f for f in SLOT_OBSERVED if f not in observed]
        if missing:
            raise LedgerError(f"a slot event needs --observed {', '.join(m + '=...' for m in missing)}")

    choose("kind", rec["kind"], KINDS)
    choose("role", rec["role"], ROLES)
    choose("policy", rec["cleanup_policy"], POLICIES)
    choose("status", rec["status"], STATUSES)

    last_seq = max((r.get("seq", 0) for r in records), default=0)
    return {
        "schema_version": SCHEMA_VERSION,
        "round_id": round_id,
        "round_slug": round_slug,
        "seq": last_seq + 1,
        "event": a.event,
        "resource_key": key,
        "kind": rec["kind"],
        "role": rec["role"],
        "parent_key": rec["parent_key"],
        "cleanup_policy": rec["cleanup_policy"],
        "selector": rec["selector"],
        "observed": rec["observed"],
        "status": rec["status"],
        "detail": a.detail,
    }


def parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="ledger.py", description="Append one event to a herdr-fleet manifest.")
    p.add_argument("manifest", help="absolute path of <round-dir>/manifest.jsonl")
    p.add_argument("event", choices=EVENTS)
    p.add_argument("resource_key")
    p.add_argument("--kind")
    p.add_argument("--role")
    p.add_argument("--parent", help="logical parent resource_key")
    p.add_argument("--policy", help="cleanup_policy")
    p.add_argument("--status")
    p.add_argument("--detail")
    p.add_argument("--selector", action="append", metavar="K=V")
    p.add_argument("--observed", action="append", metavar="K=V")
    p.add_argument("--round-id")
    p.add_argument("--round-slug")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    a = parse(argv)
    if not os.path.isabs(a.manifest):
        print("ledger: the manifest path must be absolute (the recorded round directory)", file=sys.stderr)
        return 2
    if not os.path.isdir(os.path.dirname(a.manifest)):
        print(f"ledger: no round directory at {os.path.dirname(a.manifest)}", file=sys.stderr)
        return 2
    with open(a.manifest, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            rec = build(read_records(fh), a)
        except LedgerError as exc:
            print(f"ledger: {exc}", file=sys.stderr)
            return 1
        fh.seek(0, os.SEEK_END)
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    print(f"seq {rec['seq']} {rec['event']} {rec['resource_key']} {rec['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
