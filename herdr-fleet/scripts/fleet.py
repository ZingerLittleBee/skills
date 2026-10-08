#!/usr/bin/env python3
"""Round mechanics for herdr-fleet: one command per orchestrator decision.

SKILL.md decides *what* to do; this script does the bookkeeping: herdr
calls, the write-ahead manifest (via ledger.py), sha binding, the serial
check queue, review briefs, verdict validation and cleanup. Every command
prints a short plain-text result meant to be read whole.

    fleet.py init --repo PATH --slug SLUG [--slots FILE]
    fleet.py --round DIR <command> [...]      (init prints this prefix)

Commands after init:
    resolve [--override SLOT=model,...]   re-probe CLIs; per-round slot override
    package SLUG --slot S [--grade G] [--prep CMD] [--copy REL]... [--check CMD]
    implement PKG --brief FILE [--name NAME] [--slot S]
    prompt NAME (--file FILE | --text TEXT | --resend)
    wait [--timeout SEC]           block until something needs a decision
    submit PKG | accept PKG        (wait does both on its own when it can)
    send-back PKG [--note TEXT] [--extend] | drop PKG --reason TEXT
    recheck PKG [--prep [CMD]] [--copy REL] [--check CMD]
    adjudicate PKG --finding TEXT
    fallback NAME --reason TEXT [--cli] | restart NAME | stop NAME
    merge --order A,B,... [--prep CMD] [--suite CMD] | merge | merge --abort
    status | cleanup

Standard library only; Python 3.9+.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

SELF = Path(__file__).resolve()
SKILL_DIR = SELF.parent.parent
SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{0,18}$")
SETTLED = ("idle", "done")
SHARED_BRANCHES = re.compile(r"^(main|master|trunk|develop|development|release/.*|HEAD)$")
# kind -> (binary, herdr integration target, exit command)
KINDS = {
    "claude": ("claude", "claude", "/exit"), "codex": ("codex", "codex", "/exit"),
    "cursor": ("cursor-agent", "cursor", "/exit"), "grok": ("grok", "grok", "/quit"),
    "agy": ("agy", "antigravity-cli", "/exit"), "droid": ("droid", "droid", "/exit"),
    "devin": ("devin", "devin", "/exit"), "omp": ("omp", "omp", "/exit"),
    "gemini": ("gemini", "gemini", "/quit"), "opencode": ("opencode", "opencode", "/exit"),
    "pi": ("pi", "pi", "/exit"), "copilot": ("copilot", "copilot", "/exit"),
}
REQUIRED_SLOTS = ("smol", "default", "slow", "review")


class FleetError(Exception):
    pass


# ----------------------------------------------------------------- utils ---

def run(cmd: list[str], cwd: str | None = None, check: bool = False, timeout: float = 120) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise FleetError(f"{' '.join(cmd[:4])}... failed: {(p.stderr or p.stdout).strip()[-400:]}")
    return p


def git(path: str, *args: str, check: bool = True) -> str:
    return run(["git", "-C", path, *args], check=check).stdout.strip()


def herdr(*args: str, timeout: float = 120) -> dict:
    p = run(["herdr", *args], timeout=timeout)
    try:
        return json.loads(p.stdout) if p.stdout.strip() else {"result": {}}
    except json.JSONDecodeError:
        return {"error": {"code": "non_json", "message": (p.stdout + p.stderr).strip()[-400:]}}


def herdr_ok(*args: str, timeout: float = 120) -> dict:
    out = herdr(*args, timeout=timeout)
    if "error" in out:
        raise FleetError(f"herdr {' '.join(args[:2])}: {out['error'].get('code')}: {out['error'].get('message')}")
    return out.get("result", {})


def agents_listed() -> list[dict]:
    return herdr("agent", "list").get("result", {}).get("agents", [])


def agents_live() -> dict[str, dict]:
    return {a["name"]: a for a in agents_listed() if a.get("name")}


def screen(target: str, lines: int = 15) -> str:
    """The visible screen's last non-blank rows (agent or pane read print plain text)."""
    p = run(["herdr", "agent" if ":" not in target else "pane", "read", target, "--source", "visible"])
    text = p.stdout if p.returncode == 0 and not p.stdout.startswith('{"error"') else ""
    rows = [r.rstrip() for r in text.splitlines() if r.strip()]
    return "\n".join("    | " + r[:160] for r in rows[-lines:])


def pane_idle(pane: str) -> bool:
    info = herdr("pane", "process-info", "--pane", pane).get("result", {}).get("process_info", {})
    fg = info.get("foreground_processes") or []
    return bool(fg) and all(p.get("pid") == info.get("shell_pid") for p in fg)


def short(sha: str | None) -> str:
    return (sha or "-")[:7]


def state_root() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "herdr-fleet"


def slots_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "herdr-fleet"
    for name in ("slots.yml", "slots.yaml", "slots.json"):
        if (base / name).exists():
            return base / name
    return base / "slots.yml"


# ---------------------------------------------------------- tiny YAML ---
# The catalog uses a small YAML subset: block mappings, block lists, flow
# lists of scalars and flow mappings of scalars. Anything else is an error.

def _strip_comment(line: str) -> str:
    out, quote = [], None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(s: str):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        return s[1:-1]
    return s


def _split_flow(body: str) -> list[str]:
    parts, cur, quote, depth = [], [], None, 0
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return [p.strip() for p in parts]


def _value(s: str):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        return [_value(p) for p in _split_flow(s[1:-1])]
    if s.startswith("{") and s.endswith("}"):
        out = {}
        for p in _split_flow(s[1:-1]):
            k, _, v = p.partition(":")
            out[_scalar(k)] = _value(v)
        return out
    return _scalar(s)


def parse_yaml(text: str):
    lines = [(len(l) - len(l.lstrip()), l.strip()) for l in map(_strip_comment, text.splitlines()) if l.strip()]

    def block(i: int, indent: int):
        if lines[i][1].startswith("- "):
            items = []
            while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("- "):
                rest = lines[i][1][2:].strip()
                if ":" in rest and not rest.startswith(("{", "[", "\"", "'")):
                    # "- key: v" starts a mapping item
                    sub = [(indent + 2, rest)]
                    j = i + 1
                    while j < len(lines) and lines[j][0] > indent:
                        sub.append(lines[j])
                        j += 1
                    items.append(parse_lines(sub))
                    i = j
                else:
                    items.append(_value(rest))
                    i += 1
            return items, i
        out = {}
        while i < len(lines) and lines[i][0] == indent:
            key, _, rest = lines[i][1].partition(":")
            if rest.strip():
                out[_scalar(key)] = _value(rest)
                i += 1
            elif i + 1 < len(lines) and lines[i + 1][0] > indent:
                out[_scalar(key)], i = block(i + 1, lines[i + 1][0])
            else:
                out[_scalar(key)] = None
                i += 1
        return out, i

    def parse_lines(sub):
        nonlocal lines
        saved, lines = lines, sub
        try:
            val, _ = block(0, sub[0][0])
        finally:
            lines = saved
        return val

    if not lines:
        return {}
    val, end = block(0, lines[0][0])
    if end != len(lines):
        raise FleetError(f"slots file: cannot parse near {lines[end][1]!r}; keep to the documented shape")
    return val


def load_catalog(path: Path) -> dict:
    if not path.exists():
        raise FleetError(f"no slot catalog at {path}: ask the user which models and CLIs they have "
                         f"(shape: references/slots.md) and write it")
    text = path.read_text()
    data = json.loads(text) if path.suffix == ".json" else parse_yaml(text)
    models, slots = data.get("models") or {}, data.get("slots") or {}
    for name, m in models.items():
        if not isinstance(m, dict) or not m.get("vendor") or not m.get("providers"):
            raise FleetError(f"model {name}: needs vendor and providers")
    for s, names in slots.items():
        missing = [n for n in names or [] if n not in models]
        if missing:
            raise FleetError(f"slot {s} names unknown models: {', '.join(missing)}")
    return {"models": models, "slots": {k: list(v or []) for k, v in slots.items()}}


# ---------------------------------------------------------------- round ---

class Round:
    def __init__(self, path: str):
        self.dir = Path(path).resolve()
        if not (self.dir / "state.json").exists():
            raise FleetError(f"no round at {self.dir} (state.json missing)")
        self.manifest = str(self.dir / "manifest.jsonl")

    @contextmanager
    def state(self):
        with open(self.dir / "state.lock", "a+") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            st = json.loads((self.dir / "state.json").read_text())
            yield st
            tmp = self.dir / "state.json.tmp"
            tmp.write_text(json.dumps(st, indent=1, sort_keys=True))
            tmp.replace(self.dir / "state.json")

    def read(self) -> dict:
        return json.loads((self.dir / "state.json").read_text())

    def log(self, event: str, key: str, **kw) -> None:
        ledger.append(self.manifest, event, key, **kw)

    def path(self, name: str) -> str:
        return str(self.dir / name)

    def prefix(self) -> str:
        return f"python3 {SELF} --round {self.dir}"


# ---------------------------------------------------------------- slots ---

def probe_kinds(kinds: set[str]) -> dict[str, dict]:
    status_text = run(["herdr", "integration", "status"]).stdout
    integ = {}
    for line in status_text.splitlines():
        name, sep, rest = line.partition(":")
        if sep:
            integ[name.split(" (")[0].strip()] = rest.strip().split(" (")[0]
    out = {}
    for k in sorted(kinds):
        binary, target, _ = KINDS.get(k, (k, k, "/exit"))
        out[k] = {"binary": bool(shutil.which(binary)), "target": target,
                  "integration": integ.get(target, "unknown")}
    return out


def pairs_for(st: dict, slot: str, avoid_vendor: str | None = None) -> list[dict]:
    cat = st["catalog"]
    out = []
    for model in st["slot_lists"].get(slot, []):
        m = cat["models"][model]
        if avoid_vendor and m["vendor"] == avoid_vendor:
            continue
        for prov in m["providers"]:
            kind = prov["kind"]
            probe = st["kinds"].get(kind, {})
            if not probe.get("binary") or probe.get("integration") != "current":
                continue
            if kind in st["failed_kinds"] or f"{model}|{kind}" in st["failed_pairs"]:
                continue
            out.append({"slot": slot, "model": model, "vendor": m["vendor"], "kind": kind,
                        "args": str(prov.get("args", ""))})
    return out


def resolve_slots(st: dict) -> list[str]:
    notes = []
    for slot in st["slot_lists"]:
        ps = pairs_for(st, slot)
        st["active"][slot] = ps[0] if ps else None
    for slot in REQUIRED_SLOTS:
        if not st["active"].get(slot):
            notes.append(f"BLOCKER required slot {slot} has no usable model")
    for slot in ("smol", "default", "slow", "hard", "ui"):
        a = st["active"].get(slot)
        if a and not pairs_for(st, "review", avoid_vendor=a["vendor"]):
            notes.append(f"BLOCKER no review model with a vendor other than {a['vendor']} (slot {slot})")
    return notes


def record_slot(rnd: Round, st: dict, slot: str, replaced: dict | None = None, why: str | None = None) -> None:
    a = st["active"].get(slot)
    if not a:
        return
    obs = {"model": a["model"], "provider_kind": a["kind"], "args": a["args"]}
    if replaced:
        obs["replaced"] = {"model": replaced["model"], "provider_kind": replaced["kind"], "reason": why or ""}
    rnd.log("slot", f"slot/{slot}", observed=obs, detail=why)


# ----------------------------------------------------------------- init ---

def cmd_init(a) -> None:
    if not SLUG_RE.match(a.slug):
        raise FleetError("round slug: 1-19 chars, lowercase letter first, then [a-z0-9_-]")
    if "error" in herdr("workspace", "list"):
        raise FleetError("herdr server is not reachable; start herdr first")
    repo = git(a.repo, "rev-parse", "--show-toplevel")
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    base = git(repo, "rev-parse", "HEAD")
    if git(repo, "branch", "--list", f"feat/{a.slug}"):
        raise FleetError(f"branch feat/{a.slug} exists; pick another round slug")
    catalog_path = Path(a.slots).resolve() if a.slots else slots_file()
    catalog = load_catalog(catalog_path)
    kinds = {p["kind"] for m in catalog["models"].values() for p in m["providers"]}

    round_id = time.strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3)
    root = state_root()
    root.mkdir(parents=True, exist_ok=True)
    rdir = root / f"{a.slug}-{round_id}"
    rdir.mkdir()
    ledger.append(str(rdir / "manifest.jsonl"), "created", "round/dir", kind="dir", role="round-dir",
                  policy="report-only", selector={"path": str(rdir)}, observed={"path": str(rdir)},
                  round_id=round_id, round_slug=a.slug)
    st = {"round_id": round_id, "slug": a.slug, "repo": repo, "branch": branch, "base": base,
          "catalog": catalog, "catalog_path": str(catalog_path), "slot_lists": dict(catalog["slots"]), "kinds": probe_kinds(kinds),
          "active": {}, "failed_pairs": [], "failed_kinds": [], "packages": {}, "agents": {},
          "checks": {}, "merge": None, "seq": 0}
    notes = resolve_slots(st)
    (rdir / "state.json").write_text(json.dumps(st, indent=1, sort_keys=True))
    rnd = Round(str(rdir))
    for slot in st["active"]:
        record_slot(rnd, st, slot)
    _write_rules(rnd)

    print(f"round {a.slug} id {round_id}")
    print(f"fleet: {rnd.prefix()}")
    print(f"repo {repo} branch {branch} base {base}")
    if git(repo, "status", "--porcelain"):
        print("note: main checkout has uncommitted changes; the round starts from the base commit without them")
    for slot, p in st["active"].items():
        print(f"slot {slot}: " + (f"{p['model']} via {p['kind']} ({p['vendor']})" if p else "none"))
    for k, p in st["kinds"].items():
        if not p["binary"]:
            print(f"kind {k}: binary missing, its providers are skipped")
        elif p["integration"] != "current":
            print(f"kind {k}: integration {p['integration']}; `herdr integration install {p['target']}` "
                  f"changes the user's CLI config: ask first, then rerun `resolve`")
    legacy = Path(os.environ.get("TMPDIR") or "/tmp").glob("herdr-fleet-*")  # rounds of the previous layout
    for d in sorted([*root.iterdir(), *legacy]):
        if d.is_dir() and d != rdir and _open_resources(d):
            print(f"leftover round with open resources: {d} (see references/recovery.md)")
    for n in notes:
        print(n)


def cmd_resolve(rnd: Round, a) -> None:
    with rnd.state() as st:
        before = dict(st["active"])
        # The user may have edited the catalog (a dead model replaced); failed pairs stay failed.
        st["catalog"] = load_catalog(Path(st["catalog_path"]))
        models = st["catalog"]["models"]
        for ov in a.override or []:
            slot, _, names = ov.partition("=")
            names = [m for m in names.split(",") if m]
            unknown = [m for m in names if m not in models]
            if unknown:
                raise FleetError(f"not in the catalog: {', '.join(unknown)}")
            st.setdefault("overrides", {})[slot] = names
        overrides = {k: v for k, v in st.get("overrides", {}).items() if all(m in models for m in v)}
        st["slot_lists"] = {**st["catalog"]["slots"], **overrides}
        st["kinds"] = probe_kinds({p["kind"] for m in models.values() for p in m["providers"]})
        notes = resolve_slots(st)
        for slot in st["active"]:
            if st["active"][slot] != before.get(slot):
                record_slot(rnd, st, slot, why=f"override {' '.join(a.override)}" if a.override else "resolve")
    for slot, p in st["active"].items():
        print(f"slot {slot}: " + (f"{p['model']} via {p['kind']} ({p['vendor']})" if p else "none"))
    for n in notes:
        print(n)


def _open_resources(d: Path) -> bool:
    m = d / "manifest.jsonl"
    if not m.exists():
        return False
    last = {}
    for line in m.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            return True
        if r.get("kind") not in ("slot", "dir"):
            last[r["resource_key"]] = r.get("status")
    return any(s in ("planned", "live") for s in last.values())


RULES = """# Rules for every fleet implementer

- Read the repo's convention files (CLAUDE.md / AGENTS.md) and the files your brief names before editing.
- Work only in your current directory (your worktree). Never touch another checkout.
- Write tests for what you change, but do not run the full build or test suite: the orchestrator runs
  checks one at a time across all worktrees, because parallel builds fight over shared caches. A single
  fast unit test of your own change is fine.
- Commit on your branch with the repo's commit convention (Conventional Commits when unsure: imperative,
  lowercase subject under 72 characters). No Co-Authored-By trailers or tool watermarks. Never push,
  never rewrite a commit (no reset, rebase or amend).
- End of every turn: write the summary file named in the prompt. First line exactly `DONE` or `QUESTION`,
  then what changed (file references) and anything skipped or uncertain; after `QUESTION`, the question.
  Reply with only the summary path.
"""


def _write_rules(rnd: Round) -> None:
    Path(rnd.path("implementer-rules.md")).write_text(RULES)


# -------------------------------------------------------------- packages ---

def cmd_package(rnd: Round, a) -> None:
    if not SLUG_RE.match(a.slug):
        raise FleetError("package slug: 1-19 chars, lowercase letter first, then [a-z0-9_-]")
    st = rnd.read()
    if a.slug in st["packages"] or a.slug in ("merge", st["slug"]):
        raise FleetError(f"package {a.slug} already exists")
    if a.slot not in st["active"] or not st["active"][a.slot]:
        raise FleetError(f"slot {a.slot} has no usable model")
    if git(st["repo"], "branch", "--list", f"feat/{a.slug}"):
        raise FleetError(f"branch feat/{a.slug} exists; pick another slug")
    pkg = _create_worktree(rnd, st, a.slug, f"feat/{a.slug}", a.slug, merge=False)
    pkg.update(slot=a.slot, grade=a.grade or a.slot, check_cmd=a.check, prep_cmd=a.prep, copy=a.copy or [])
    with rnd.state() as s:
        s["packages"][a.slug] = pkg
    line = f"package {a.slug}: {pkg['path']} (workspace {pkg['workspace']}, pane {pkg['root_pane']})"
    if a.prep or a.copy:
        cid = _queue_check(rnd, a.slug, "prep", None, _prep_commands(st["repo"], pkg["path"], a.copy, a.prep))
        line += f"; prep queued ({cid})"
    print(line)


def _create_worktree(rnd: Round, st: dict, key: str, branch: str, label: str, merge: bool) -> dict:
    wk, bk, pk = (("round/merge-worktree", "round/merge-target", "round/merge-root-pane") if merge else
                  (f"package/{key}/worktree", f"package/{key}/branch", f"package/{key}/root-pane"))
    rnd.log("intent", wk, kind="worktree", role="merge-worktree" if merge else "package-container",
            policy="remove-when-merged", selector={"label": label, "branch": branch})
    rnd.log("intent", bk, kind="branch", role="merge-target" if merge else "package-branch",
            policy="report-only" if merge else "remove-when-merged", parent=wk, selector={"branch": branch})
    rnd.log("intent", pk, kind="pane", role="container-root-pane", policy="close-container", parent=wk,
            selector={"label": label})
    out = herdr("worktree", "create", "--cwd", st["repo"], "--branch", branch, "--base", st["base"],
                "--label", label, "--no-focus")
    if "error" in out:
        err = f"{out['error'].get('code')}: {out['error'].get('message')}"
        for k in (wk, bk, pk):
            rnd.log("state", k, status="failed", detail=err)
        raise FleetError(f"worktree create failed: {err}")
    res = out["result"]
    path = res["worktree"]["path"]
    ws = res["workspace"]["workspace_id"]
    pane = res["root_pane"]["pane_id"]
    rnd.log("created", wk, observed={"path": path, "workspace_id": ws})
    rnd.log("created", bk, observed={"branch": branch, "base": st["base"]})
    rnd.log("created", pk, observed={"pane_id": pane, "workspace_id": ws, "path": path})
    return {"path": path, "workspace": ws, "root_pane": pane, "branch": branch, "review_pane": None,
            "candidate": None, "accepted": None, "prev_candidate": None, "review_from": None, "cycles": 0,
            "status": "open", "impl": None, "reviewer": None, "verdict": None, "merge": merge}


def _prep_commands(repo: str, path: str, copies: list[str], prep: str | None) -> str:
    parts = []
    for rel in copies or []:
        src, dst = Path(repo) / rel, Path(path) / rel
        parts.append(f"rm -rf {shlex.quote(str(dst))} && mkdir -p {shlex.quote(str(dst.parent))} && "
                     f"cp -R {shlex.quote(str(src))} {shlex.quote(str(dst))}")
    if prep:
        parts.append(prep)
    return " && ".join(parts) or "true"


# ---------------------------------------------------------------- checks ---

def _queue_check(rnd: Round, pkg: str, phase: str, sha: str | None, commands: str) -> str:
    with rnd.state() as st:
        st["seq"] += 1
        cid = f"{pkg}-{phase}-{short(sha) if sha else 'base'}-{st['seq']}"
        path = st["packages"][pkg]["path"] if pkg != "merge" else st["merge"]["path"]
        st["checks"][cid] = {"package": pkg, "phase": phase, "sha": sha, "path": path, "commands": commands,
                             "report": rnd.path(f"{cid}.md"), "log": rnd.path(f"{cid}.log"),
                             "status": "queued", "reported": False}
    out = open(rnd.path(f"{cid}.runner.log"), "ab")
    proc = subprocess.Popen([sys.executable, str(SELF), "--round", str(rnd.dir), "_check", cid],
                            stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            start_new_session=True)
    with rnd.state() as st:
        st["checks"][cid]["pid"] = proc.pid
    return cid


def _binding(path: str, sha: str) -> str | None:
    dirty = git(path, "status", "--porcelain", check=False)
    head = git(path, "rev-parse", "HEAD", check=False)
    if dirty:
        return "tree not clean:\n" + dirty[:800]
    if head != sha:
        return f"HEAD is {head}, expected {sha}"
    return None


def cmd_check_runner(rnd: Round, a) -> None:
    """Runs detached: waits for the round-wide check lock, then one check."""
    with open(rnd.path("check.lock"), "a+") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        c = rnd.read()["checks"][a.cid]
        with rnd.state() as st:
            st["checks"][a.cid]["status"] = "running"
        problem = _binding(c["path"], c["sha"]) if c["sha"] else None
        if problem:
            rc, verdict = 1, f"FAIL-BINDING {c['sha']}"
            Path(c["log"]).write_text(f"before the run: {problem}\n")
        else:
            with open(c["log"], "w") as log:
                rc = subprocess.run(["bash", "-o", "pipefail", "-c", c["commands"]], cwd=c["path"],
                                    stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL).returncode
            after = _binding(c["path"], c["sha"]) if c["sha"] else None
            if after:
                rc = 1
                with open(c["log"], "a") as log:
                    log.write(f"\nafter the run: {after}\n")
            verdict = ("PASS" if rc == 0 else ("FAIL-DIRTY" if after else "FAIL")) + f" {c['sha'] or 'base'}"
        Path(c["report"]).write_text(f"{verdict}\n\n$ {c['commands']}\n\n" + Path(c["log"]).read_text())
        with rnd.state() as st:
            st["checks"][a.cid].update(status=verdict.split()[0], rc=rc)


def _check_result(rnd: Round, cid: str, c: dict) -> str:
    line = f"check {c['package']} {c['phase']} {short(c['sha']) if c['sha'] else 'base'}: {c['status']}"
    if c["status"] != "PASS":
        tail = Path(c["log"]).read_text().splitlines()[-12:] if Path(c["log"]).exists() else []
        line += f"  report {c['report']}\n" + "\n".join("    | " + t[:160] for t in tail)
    return line


# ---------------------------------------------------------------- agents ---

def _start(rnd: Round, st: dict, name: str, role: str, pkg_key: str, pair: dict, pane: str,
           ledger_role: str) -> tuple[str, str]:
    """Start one agent; returns (status, screen-or-message). Records the ledger either way."""
    key = f"agent/{name}"
    parent = (f"package/{pkg_key}/worktree" if pkg_key != "merge" else "round/merge-worktree")
    rnd.log("intent", key, kind="agent", role=ledger_role, policy="close-aux", parent=parent,
            selector={"name": name, "slot": pair["slot"], "model": pair["model"]})
    out = herdr("agent", "start", name, "--kind", pair["kind"], "--pane", pane, "--timeout", "90000",
                "--", *shlex.split(pair["args"]), timeout=150)
    err = out.get("error")
    present = name in agents_live() if err else True
    obs = {"name": name, "pane_id": pane, "slot": pair["slot"], "model": pair["model"],
           "provider_kind": pair["kind"], "args": pair["args"]}
    if err and not present:
        msg = f"{err.get('code')}: {err.get('message')}"
        rnd.log("state", key, status="failed", detail=f"start failed: {msg}")
        return "failed", msg + "\n" + screen(pane, 10)
    rnd.log("created", key, observed=obs)
    st["agents"][name] = {"name": name, "role": role, "package": pkg_key, "pane": pane, "status": "live",
                          "slot": pair["slot"], "model": pair["model"], "vendor": pair["vendor"],
                          "kind": pair["kind"], "args": pair["args"], "summary_n": 0, "summary": None,
                          "pending": None, "last_prompt": None, "reported_seq": None,
                          "restarts": st["agents"].get(name, {}).get("restarts", 0)}
    if err:
        return "blocked", f"{err.get('code')}: startup stopped at a screen\n" + screen(name)
    return "ready", ""


def _prompt_text(rnd: Round, ag: dict, body: str) -> str:
    if ag["role"] == "reviewer":
        return body
    ag["summary_n"] += 1
    ag["summary"] = rnd.path(f"{ag['name']}-summary-{ag['summary_n']}.md")
    return f"{body} Summary file for this turn: {ag['summary']}"


def _send(rnd: Round, st: dict, name: str, body: str) -> str:
    ag = st["agents"][name]
    text = _prompt_text(rnd, ag, body)
    ag["last_prompt"] = text
    if _prep_busy(st, ag["package"]):
        ag["pending"] = text
        return "queued until the worktree's prep check finishes"
    live = agents_live().get(name)
    if live and live.get("agent_status") in SETTLED and _deliver(ag, live, text):
        return "sent"
    ag["pending"] = text
    return "queued until the agent settles (it is " + (live or {}).get("agent_status", "gone") + ")"


def _prep_busy(st: dict, pkg_key: str) -> bool:
    return any(c["package"] == pkg_key and c["phase"] == "prep" and c["status"] in ("queued", "running")
               for c in st["checks"].values())


def _deliver(ag: dict, live: dict, text: str) -> bool:
    """Prompt a settled agent; remember the state seq it had, so wait knows the turn is still to come."""
    if "error" in herdr("agent", "prompt", ag["name"], text):
        return False
    ag.update(pending=None, sent_seq=live.get("state_change_seq"), sent_at=time.time())
    return True


def _brief_body(rnd: Round, brief: str) -> str:
    return f"Read {rnd.path('implementer-rules.md')} and then {brief}, and complete the task the brief describes."


def cmd_implement(rnd: Round, a) -> None:
    st = rnd.read()
    pkg_key = a.package
    pkg = st["merge"] if pkg_key == "merge" else st["packages"].get(pkg_key)
    if not pkg:
        raise FleetError(f"no package {pkg_key}" + (" (run merge first)" if pkg_key == "merge" else ""))
    name = a.name or pkg_key
    slot = a.slot or pkg.get("slot") or "default"
    with rnd.state() as st:
        pkg = st["merge"] if pkg_key == "merge" else st["packages"][pkg_key]
        prev = pkg.get("impl")
        if prev and st["agents"].get(prev, {}).get("status") == "live":
            raise FleetError(f"{prev} is still live in this worktree; stop it first (one writer at a time)")
        pair = st["active"].get(slot)
        if not pair:
            raise FleetError(f"slot {slot} has no usable model")
        status, msg = _start(rnd, st, name, "implementer", pkg_key, pair, pkg["root_pane"],
                             "merge-implementer" if pkg_key == "merge" else "package-implementer")
        if status == "failed":
            print(f"{name}: start failed on {pair['model']} via {pair['kind']}\n{msg}")
            print(f"-> if the CLI or model is unusable: fallback {name} --reason '...' (agent stays recorded)")
            st["agents"][name] = {"name": name, "role": "implementer", "package": pkg_key, "status": "failed",
                                  "slot": slot, "model": pair["model"], "vendor": pair["vendor"],
                                  "kind": pair["kind"], "args": pair["args"], "pane": pkg["root_pane"],
                                  "brief": a.brief, "summary_n": 0, "restarts": 0}
            pkg["impl"] = name
            return
        pkg["impl"] = name
        pkg["review_from"] = git(pkg["path"], "rev-parse", "HEAD")
        st["agents"][name]["brief"] = a.brief
        sent = _send(rnd, st, name, _brief_body(rnd, a.brief))
    print(f"{name}: {pair['model']} via {pair['kind']} in {pkg['root_pane']}; brief {sent}")
    if msg:
        print(msg)


def cmd_prompt(rnd: Round, a) -> None:
    with rnd.state() as st:
        ag = st["agents"].get(a.name)
        if not ag or ag["status"] != "live":
            raise FleetError(f"{a.name} is not live")
        if a.resend:
            if not ag.get("last_prompt"):
                raise FleetError("nothing to resend")
            live = agents_live().get(a.name) or {}
            print("resent" if _deliver(ag, live, ag["last_prompt"]) else "agent is not settled; wait first")
            return
        body = f"Read {a.file} and act on it." if a.file else a.text
        print(f"{a.name}: {_send(rnd, st, a.name, body)}")


def _stop_agent(rnd: Round, st: dict, name: str, close_pane: bool, status: str = "removed",
                detail: str | None = None) -> str:
    ag = st["agents"].get(name)
    if not ag or ag["status"] != "live":
        return f"{name} already gone"
    live = agents_live()
    if name in live:
        exit_cmd = KINDS.get(ag["kind"], ("", "", "/exit"))[2]
        if live[name].get("agent_status") == "working":
            herdr("agent", "send-keys", name, "ctrl+c")
            time.sleep(1)
        herdr("pane", "run", ag["pane"], exit_cmd)
        for i in range(20):
            time.sleep(1)
            if name not in agents_live():
                break
            if i in (6, 12):
                herdr("pane", "send-keys", ag["pane"], "ctrl+c")
                herdr("pane", "send-keys", ag["pane"], "ctrl+d")
    gone = name not in agents_live()
    ag["status"] = "removed" if gone else "live"
    if not gone:
        return f"{name} did not exit; read its screen and stop it by hand"
    rnd.log("state", f"agent/{name}", status=status, detail=detail)
    if close_pane and ag.get("own_pane") and pane_idle(ag["pane"]):
        herdr("pane", "close", ag["pane"])
        rnd.log("state", ag["own_pane"], status="removed")
        for p in list(st["packages"].values()) + ([st["merge"]] if st["merge"] else []):
            if p.get("review_pane") == ag["pane"]:
                p["review_pane"] = None
    return f"{name} stopped"


def cmd_stop(rnd: Round, a) -> None:
    with rnd.state() as st:
        print(_stop_agent(rnd, st, a.name, close_pane=True))


def _next_pair(st: dict, ag: dict, avoid_vendor: str | None) -> dict | None:
    if ag["role"] == "adjudicator":
        for slot in ("slow", "review"):
            ps = pairs_for(st, slot, avoid_vendor)
            if ps:
                return ps[0]
        return None
    ps = pairs_for(st, ag["slot"], avoid_vendor)
    if ps:
        return ps[0]
    if ag["slot"] == "ui":
        pkg = st["packages"].get(ag["package"], {})
        ps = pairs_for(st, pkg.get("grade") or "default", avoid_vendor)
        return ps[0] if ps else None
    return None


def _impl_vendor(st: dict, pkg_key: str) -> str | None:
    pkg = st["merge"] if pkg_key == "merge" else st["packages"].get(pkg_key, {})
    impl = st["agents"].get(pkg.get("impl") or "", {})
    return impl.get("vendor")


def _rebrief(rnd: Round, st: dict, name: str) -> str:
    ag = st["agents"][name]
    if ag["role"] == "implementer":
        pkg = st["merge"] if ag["package"] == "merge" else st["packages"][ag["package"]]
        body = (f"You replace an agent that stopped mid-task. First run `git log --oneline "
                f"{pkg['review_from'] or st['base']}..HEAD` and `git status` here and continue from the "
                f"committed state. " + _brief_body(rnd, ag["brief"]))
    else:
        body = ag["last_prompt"] or ""
    return _send(rnd, st, name, body)


def cmd_fallback(rnd: Round, a) -> None:
    with rnd.state() as st:
        ag = st["agents"].get(a.name)
        if not ag:
            raise FleetError(f"no agent {a.name}")
        old = {k: ag[k] for k in ("slot", "model", "vendor", "kind", "args")}
        if a.cli:
            st["failed_kinds"].append(ag["kind"])
        else:
            st["failed_pairs"].append(f"{ag['model']}|{ag['kind']}")
        if ag["status"] == "live":
            msg = _stop_agent(rnd, st, a.name, close_pane=False, status="failed", detail=a.reason)
            if "did not exit" in msg:
                raise FleetError(msg)
        avoid = _impl_vendor(st, ag["package"]) if ag["role"] in ("reviewer", "adjudicator") else None
        pair = _next_pair(st, ag, avoid)
        st["active"][ag["slot"]] = pairs_for(st, ag["slot"])[0] if pairs_for(st, ag["slot"]) else None
        record_slot(rnd, st, ag["slot"], replaced=old, why=a.reason)
        if not pair:
            print(f"{a.name}: no model left for slot {ag['slot']}"
                  + (f" with a vendor other than {avoid}" if avoid else "") + ": ask the user")
            return
        last_prompt, brief, role = ag.get("last_prompt"), ag.get("brief"), ag["role"]
        ledger_role = {"implementer": "merge-implementer" if ag["package"] == "merge" else "package-implementer",
                       "reviewer": "merge-reviewer" if ag["package"] == "merge" else "package-reviewer",
                       "adjudicator": "package-reviewer"}[role]
        own = ag.get("own_pane")
        status, msg = _start(rnd, st, a.name, role, ag["package"], pair, ag["pane"], ledger_role)
        if status == "failed":
            st["agents"][a.name] = {**ag, **pair, "status": "failed"}
            print(f"{a.name}: replacement {pair['model']} via {pair['kind']} failed too\n{msg}")
            return
        st["agents"][a.name].update(brief=brief, last_prompt=last_prompt, own_pane=own,
                                    verdict=ag.get("verdict"), grades=ag.get("grades"))
        sent = _rebrief(rnd, st, a.name)
    print(f"{a.name}: now {pair['model']} via {pair['kind']}; re-brief {sent}")
    if msg:
        print(msg)


def cmd_restart(rnd: Round, a) -> None:
    with rnd.state() as st:
        ag = st["agents"].get(a.name)
        if not ag:
            raise FleetError(f"no agent {a.name}")
        if a.name in agents_live():
            raise FleetError(f"{a.name} is still listed; read its screen instead")
        if ag.get("restarts", 0) >= 1:
            print(f"{a.name} vanished twice on {ag['model']} via {ag['kind']}: treat the pair as dead, run "
                  f"`fallback {a.name} --reason 'vanished twice'`")
            return
        if ag["status"] == "live":
            rnd.log("state", f"agent/{a.name}", status="failed", detail="vanished")
        pair = {k: ag[k] for k in ("slot", "model", "vendor", "kind", "args")}
        saved = {k: ag.get(k) for k in ("brief", "last_prompt", "own_pane", "verdict", "grades")}
        ledger_role = {"implementer": "package-implementer", "reviewer": "package-reviewer",
                       "adjudicator": "package-reviewer"}[ag["role"]]
        if ag["package"] == "merge":
            ledger_role = ledger_role.replace("package", "merge")
        status, msg = _start(rnd, st, a.name, ag["role"], ag["package"], pair, ag["pane"], ledger_role)
        if status == "failed":
            print(f"{a.name}: restart failed\n{msg}")
            return
        st["agents"][a.name].update(restarts=1, **saved)
        sent = _rebrief(rnd, st, a.name)
    print(f"{a.name}: restarted on {pair['model']} via {pair['kind']}; re-brief {sent}")


# ---------------------------------------------------------------- review ---

REVIEW = """# Review: {pkg} at {sha}

You are a read-only reviewer. Edit nothing, commit nothing, run no build or test suite, start no agents.

- Package brief (scope and acceptance criteria): {brief}
- Checkout: {path}
- Grade exactly: `git -C {path} diff {base} {sha}`{regrade}
- Read surrounding code where the diff's effects demand it.

A finding must have a provable impact on correctness, security, data integrity or an acceptance
criterion; point at a file and line; be unintended; and be introduced by this diff. Style, naming and
"consider" remarks are not findings. Priorities: P0/P1 block (a criterion fails, correctness or security
breaks, the merge is endangered); P2/P3 do not. Scale the depth to the change: a small mechanical diff
gets a short verdict.

Also name the one assumption shared by the implementation and its tests that nothing outside them has
validated (a provider contract, a real-system response), or null if none applies.

Write the verdict as JSON to {verdict} and reply with only that path:

{{"candidate_sha": "{sha}", "overall_correctness": "correct | incorrect", "explanation": "<one paragraph>",
 "findings": [{{"title": "", "body": "<what, why, how to verify>", "priority": "P0|P1|P2|P3",
   "file_path": "<repo-relative>", "line_start": 0, "line_end": 0}}],
 "assumption_check": {{"assumption": "<text or null>", "status": "designed | executed | not-applicable"}}}}

`overall_correctness` is "incorrect" exactly when a P0 or P1 finding exists. Use status "not-applicable"
exactly when the assumption is null.
"""


def validate_verdict(path: str, sha: str) -> tuple[str, dict | None]:
    """("valid", verdict) or (reason, None); the reason is what the reviewer must fix."""
    p = Path(path)
    if not p.exists():
        return "missing", None
    try:
        v = json.loads(p.read_text())
    except (ValueError, UnicodeDecodeError) as exc:
        return f"malformed: not JSON ({exc})", None
    problems = []
    if not isinstance(v, dict):
        return "malformed: not an object", None
    if not isinstance(v.get("candidate_sha"), str):
        problems.append("candidate_sha must be a string")
    if v.get("overall_correctness") not in ("correct", "incorrect"):
        problems.append("overall_correctness must be correct or incorrect")
    f = v.get("findings")
    if not isinstance(f, list):
        problems.append("findings must be a list")
        f = []
    for i, x in enumerate(f):
        if not isinstance(x, dict) or x.get("priority") not in ("P0", "P1", "P2", "P3") \
                or not isinstance(x.get("title"), str) or not isinstance(x.get("file_path"), str) \
                or not isinstance(x.get("line_start"), (int, float)) or isinstance(x.get("line_start"), bool):
            problems.append(f"findings[{i}] needs priority P0-P3, title, file_path and numeric line_start")
    blocking = any(isinstance(x, dict) and x.get("priority") in ("P0", "P1") for x in f)
    if (v.get("overall_correctness") == "incorrect") != blocking:
        problems.append("overall_correctness is incorrect exactly when a P0/P1 finding exists")
    ac = v.get("assumption_check")
    if not isinstance(ac, dict) or ac.get("status") not in ("designed", "executed", "not-applicable"):
        problems.append("assumption_check.status must be designed, executed or not-applicable")
    elif ac.get("assumption") is None and ac.get("status") != "not-applicable":
        problems.append("a null assumption takes status not-applicable")
    if problems:
        return "malformed: " + "; ".join(problems), None
    if v["candidate_sha"] != sha:
        return f"names {short(v['candidate_sha'])}, not {short(sha)}", None
    return "valid", v


def _verdict_line(rnd: Round, st: dict, ag: dict) -> str:
    sha = ag.get("grades")
    status, v = validate_verdict(ag.get("verdict") or "", sha or "")
    if status != "valid":
        return f"verdict {status} at {ag.get('verdict')}"
    blocking = [f"{x['priority']} {x['title']} ({x['file_path']}:{x['line_start']})"
                for x in v["findings"] if x["priority"] in ("P0", "P1")]
    ac = v.get("assumption_check") or {}
    out = f"verdict {v['overall_correctness']} on {short(sha)}"
    if blocking:
        out += "; blocking: " + "; ".join(blocking)
    nb = sum(1 for x in v["findings"] if x["priority"] not in ("P0", "P1"))
    if nb:
        out += f"; {nb} non-blocking"
    if ac.get("assumption"):
        out += f"; assumption ({ac.get('status')}): {str(ac['assumption'])[:140]}"
    return out


def _dispatch_review(rnd: Round, st: dict, pkg_key: str, sha: str, base: str, prev: str | None,
                     name: str | None = None, role: str = "reviewer", extra: str = "") -> str:
    pkg = st["merge"] if pkg_key == "merge" else st["packages"][pkg_key]
    impl_vendor = _impl_vendor(st, pkg_key)
    label = pkg.get("impl") or pkg_key
    verdict_key = label if role == "reviewer" else f"{label}-adjudicate"
    stem = label[:-len("-suite-fix")] + "-suite" if label.endswith("-suite-fix") else label
    rname = name or (f"{stem}-review" if role == "reviewer" else f"{label}-adjudicate")
    verdict = rnd.path(f"{verdict_key}-verdict-{sha}.json")
    brief_path = rnd.path(f"{rname}-{short(sha)}.md")
    regrade = ""
    if prev and pkg.get("verdict"):
        regrade = (f"\n- This is a re-grade. Prior verdict: {pkg['verdict']} (on {prev}). Confirm each blocking "
                   f"finding there is resolved, and check `git -C {pkg['path']} diff {prev} {sha}` for "
                   f"regressions and scope creep; the verdict covers the whole diff above.")
    impl = st["agents"].get(pkg.get("impl") or "", {})
    Path(brief_path).write_text(REVIEW.format(pkg=label, sha=sha, brief=impl.get("brief") or "(none)",
                                              path=pkg["path"], base=base, regrade=regrade + extra,
                                              verdict=verdict))
    body = f"Read {brief_path} and do the review it describes."
    ag = st["agents"].get(rname)
    if ag and ag["status"] == "live" and rname in agents_live():
        ag.update(verdict=verdict, grades=sha)
        return f"{rname} re-grade {_send(rnd, st, rname, body)}"
    pair = None
    if role == "adjudicator":
        for slot in ("slow", "review"):
            ps = pairs_for(st, slot, impl_vendor)
            if ps:
                pair = ps[0]
                break
    else:
        ps = pairs_for(st, "review", impl_vendor)
        pair = ps[0] if ps else None
    if not pair:
        return f"no review model with a vendor other than {impl_vendor}: ask the user"
    pane = pkg.get("review_pane")
    if not pane or not pane_idle(pane):
        key = f"{'round/merge' if pkg_key == 'merge' else 'package/' + pkg_key}/{rname}-pane"
        rnd.log("intent", key, kind="pane", role="review-pane", policy="close-aux",
                parent="round/merge-worktree" if pkg_key == "merge" else f"package/{pkg_key}/worktree",
                selector={"split_of": pkg["root_pane"]})
        res = herdr_ok("pane", "split", pkg["root_pane"], "--direction", "down", "--cwd", pkg["path"], "--no-focus")
        pane = res["pane"]["pane_id"]
        rnd.log("created", key, observed={"pane_id": pane})
        pkg["review_pane"] = pane
        own = key
    else:
        own = next((a.get("own_pane") for a in st["agents"].values() if a.get("pane") == pane), None)
    status, msg = _start(rnd, st, rname, role, pkg_key, pair, pane,
                         "merge-reviewer" if pkg_key == "merge" else "package-reviewer")
    if status == "failed":
        st["agents"][rname] = {"name": rname, "role": role, "package": pkg_key, "status": "failed",
                               "pane": pane, "own_pane": own, "verdict": verdict, "grades": sha,
                               "last_prompt": body, "restarts": 0, **pair}
        return f"{rname} start failed on {pair['model']} via {pair['kind']}: {msg}\n-> fallback {rname} --reason ..."
    st["agents"][rname].update(verdict=verdict, grades=sha, own_pane=own)
    sent = _send(rnd, st, rname, body)
    return f"{rname}: {pair['model']} via {pair['kind']}; review {sent}" + (f"\n{msg}" if msg else "")


def _pkg(st: dict, key: str) -> dict:
    pkg = st["merge"] if key == "merge" else st["packages"].get(key)
    if not pkg:
        raise FleetError(f"no package {key}" + (" (run merge first)" if key == "merge" else ""))
    return pkg


def _suite_phase(st: dict, key: str) -> bool:
    """The merge target's gate is the suite only after every merge landed (a suite fix)."""
    return key == "merge" and not st["merge"].get("conflict")


def _submit(rnd: Round, key: str) -> str:
    with rnd.state() as st:
        pkg = _pkg(st, key)
        path = pkg["path"]
        dirty = git(path, "status", "--porcelain")
        if dirty:
            return f"{key}: uncommitted changes, not a candidate; send it back:\n{dirty[:600]}"
        if git(path, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False):
            return f"{key}: merge still in progress; the implementer must commit it"
        start = pkg["review_from"] if key == "merge" else st["base"]
        sha = git(path, "rev-parse", "HEAD")
        commits = git(path, "log", "--oneline", f"{start}..{sha}")
        if not commits:
            return f"{key}: no commits since {short(start)}; re-brief or drop it"
        if pkg["candidate"] == sha and key != "merge" or (key == "merge" and pkg.get("submitted") == sha):
            return f"{key}: {short(sha)} is already the candidate"
        prev = pkg["candidate"] if key != "merge" else pkg.get("submitted")
        pkg["candidate"] = sha
        pkg["submitted"] = sha
        bk = "round/merge-target" if key == "merge" else f"package/{key}/branch"
        rnd.log("state", bk, status="live", observed={"candidate_sha": sha})
        lines = [f"{key}: candidate {short(sha)}", *("    " + c for c in commits.splitlines()[:8])]
        lines.append(_dispatch_review(rnd, st, key, sha, start, prev))
        check = st["merge"].get("suite") if _suite_phase(st, key) else (pkg.get("check_cmd") if key != "merge" else None)
    if check:
        lines.append(f"check queued ({_queue_check(rnd, key, 'suite' if key == 'merge' else 'check', sha, check)})")
    return "\n".join(lines)


def cmd_submit(rnd: Round, a) -> None:
    print(_submit(rnd, a.package))


def cmd_recheck(rnd: Round, a) -> None:
    """Rerun the prep or the current candidate's check (a transient failure, or a corrected command)."""
    st = rnd.read()
    pkg = _pkg(st, a.package)
    if a.prep is not None or a.copy:
        if a.package == "merge":
            print(f"prep queued ({_queue_check(rnd, 'merge', 'prep', None, a.prep or 'true')})")
            return
        cmds = _prep_commands(st["repo"], pkg["path"], a.copy or pkg.get("copy"), a.prep or pkg.get("prep_cmd"))
        print(f"prep queued ({_queue_check(rnd, a.package, 'prep', None, cmds)})")
        return
    suite = _suite_phase(st, a.package) or a.package == "merge"
    if a.check:
        with rnd.state() as s2:
            if a.package == "merge":
                s2["merge"]["suite"] = a.check
            else:
                s2["packages"][a.package]["check_cmd"] = a.check
    st = rnd.read()
    pkg = _pkg(st, a.package)
    cmd = st["merge"].get("suite") if a.package == "merge" else pkg.get("check_cmd")
    sha = git(pkg["path"], "rev-parse", "HEAD") if a.package == "merge" else pkg["candidate"]
    if not cmd or not sha:
        raise FleetError("nothing to check: no command or no candidate")
    if a.package == "merge":
        with rnd.state() as s2:
            if not s2["merge"].get("submitted") or s2["merge"]["accepted"] == sha:
                s2["merge"]["candidate"] = s2["merge"]["accepted"] = sha
    print(f"check queued ({_queue_check(rnd, a.package, 'suite' if suite else 'check', sha, cmd)})")


def cmd_adjudicate(rnd: Round, a) -> None:
    with rnd.state() as st:
        pkg = _pkg(st, a.package)
        if not pkg["candidate"]:
            raise FleetError("no candidate to adjudicate")
        extra = (f"\n- Adjudicate only this finding, which the re-grade raised against code the prior candidate "
                 f"already had: {a.finding}. Your verdict settles it.")
        base = pkg["review_from"] if a.package == "merge" else st["base"]
        print(_dispatch_review(rnd, st, a.package, pkg["candidate"], base, None, role="adjudicator", extra=extra))


def _gates(st: dict, key: str, pkg: dict) -> tuple[str, list[str]]:
    """("pass" | "fail" | "pending", notes) for the current candidate."""
    sha, notes, pending = pkg["candidate"], [], False
    if not sha:
        return "pending", ["no candidate"]
    if _suite_phase(st, key) and st["merge"].get("suite") or key != "merge" and pkg.get("check_cmd"):
        runs = [c for c in st["checks"].values() if c["package"] == key and c["sha"] == sha
                and c["phase"] in ("check", "suite")]
        if not runs or runs[-1]["status"] in ("queued", "running"):
            pending = True
        elif runs[-1]["status"] != "PASS":
            notes.append(f"check {runs[-1]['status']} ({runs[-1]['report']})")
    verdicts = {ag["role"]: validate_verdict(ag["verdict"], sha) for ag in st["agents"].values()
                if ag.get("package") == key and ag.get("grades") == sha and ag["role"] in ("reviewer", "adjudicator")}
    review = verdicts.get("reviewer", ("missing", None))
    adjud = verdicts.get("adjudicator")
    if review[0] != "valid":
        pending = True
    elif review[1]["overall_correctness"] == "incorrect":
        if adjud and adjud[0] == "valid" and adjud[1]["overall_correctness"] == "correct":
            pass
        elif adjud and adjud[0] != "valid":
            pending = True
        else:
            notes.append("review has blocking findings")
    if notes:
        return "fail", notes
    return ("pending" if pending else "pass"), notes


def _close_package_agents(rnd: Round, st: dict, key: str) -> list[str]:
    return [_stop_agent(rnd, st, name, close_pane=True) for name, ag in list(st["agents"].items())
            if ag.get("package") == key and ag["status"] == "live"]


def _accept(rnd: Round, key: str) -> str:
    with rnd.state() as st:
        pkg = _pkg(st, key)
        verdict, notes = _gates(st, key, pkg)
        if verdict != "pass":
            return f"{key}: not accepted ({verdict}): " + "; ".join(notes or ["a gate is still running"])
        problem = _binding(pkg["path"], pkg["candidate"])
        if problem:
            return f"{key}: not accepted: {problem}"
        pkg["accepted"] = pkg["candidate"]
        pkg["verdict"] = None
        if key == "merge":
            rnd.log("state", "round/merge-target", status="live", observed={"accepted_sha": pkg["accepted"]})
        else:
            pkg["status"] = "accepted"
            rnd.log("state", f"package/{key}/branch", status="live", observed={"accepted_sha": pkg["accepted"]})
        stops = _close_package_agents(rnd, st, key)
    nxt = " -> merge" if key == "merge" and rnd.read()["merge"].get("conflict") else ""
    return f"{key}: ACCEPTED {short(pkg['accepted'])} ({'; '.join(stops)}){nxt}"


def cmd_accept(rnd: Round, a) -> None:
    print(_accept(rnd, a.package))


def cmd_send_back(rnd: Round, a) -> None:
    with rnd.state() as st:
        pkg = _pkg(st, a.package)
        sha = pkg["candidate"]
        if not sha:
            raise FleetError(f"{a.package} has no candidate")
        paths, rejecting, failing = [], False, False
        for ag in st["agents"].values():
            if ag.get("package") == a.package and ag.get("grades") == sha:
                s, v = validate_verdict(ag.get("verdict") or "", sha)
                if s == "valid":
                    paths.append(f"verdict: {ag['verdict']}")
                    if ag["role"] == "reviewer":
                        pkg["verdict"] = ag["verdict"]
                    rejecting |= v["overall_correctness"] == "incorrect"
        for c in st["checks"].values():
            if c["package"] == a.package and c["sha"] == sha and c["phase"] != "prep" \
                    and c["status"] not in ("PASS", "queued", "running"):
                paths.append(f"failing check report: {c['report']}")
                failing = True
        costs = rejecting or (a.package == "merge" and failing)
        used = st.get("merge_cycles", 0) if a.package == "merge" else pkg["cycles"]
        if costs and used >= 2 and not a.extend:
            print(f"{a.package}: correction budget (2) spent; drop it or ask the user, then --extend")
            return
        if costs:
            used += 1
            if a.package == "merge":
                st["merge_cycles"] = used
            else:
                pkg["cycles"] = used
        impl = pkg.get("impl")
        if not impl or st["agents"].get(impl, {}).get("status") != "live":
            raise FleetError(f"{a.package} has no live implementer; implement it again")
        fb = rnd.path(f"{impl}-feedback-{short(sha)}.md")
        Path(fb).write_text(f"# Send-back for {short(sha)}\n\n" + "\n".join(f"- {p}" for p in paths)
                            + "\n\nFix every P0 and P1 finding and every failing check, and any P2 worth taking. "
                            "Commit the fix on your branch.\n" + (f"\nOrchestrator note: {a.note}\n" if a.note else ""))
        sent = _send(rnd, st, impl, f"Read {fb} and fix what it lists.")
    print(f"{a.package}: sent back (cycles used {used}/2); {sent}")


def cmd_drop(rnd: Round, a) -> None:
    with rnd.state() as st:
        pkg = st["packages"].get(a.package)
        if not pkg:
            raise FleetError(f"no package {a.package}")
        stops = _close_package_agents(rnd, st, a.package)
        pkg["status"] = "dropped"
        pkg["drop_reason"] = a.reason
    print(f"{a.package}: dropped ({a.reason}); worktree and branch kept for the user; " + "; ".join(stops))


# ------------------------------------------------------------------ wait ---

UNPICKED_AFTER = 75  # seconds a delivered prompt may sit unread before wait reports it
UNKNOWN_AFTER = 15  # seconds an agent may report no state before wait shows its screen


def _summary(ag: dict) -> tuple[str, str]:
    p = Path(ag.get("summary") or "")
    if not ag.get("summary") or not p.exists():
        return "", ""
    lines = p.read_text().splitlines()
    head = lines[0].strip() if lines else ""
    return head, " ".join(l.strip() for l in lines[1:8] if l.strip())[:400]


def _event_text(rnd: Round, st: dict, ag: dict, status: str) -> tuple[str, str | None]:
    """(event line, package to submit or None)."""
    name = ag["name"]
    if status == "blocked":
        return f"{name} BLOCKED ({ag['model']} via {ag['kind']}):\n{screen(name)}", None
    if ag["role"] == "implementer":
        head, body = _summary(ag)
        if head == "DONE":
            return f"{name} DONE", ag["package"]
        if head == "QUESTION":
            return f"{name} QUESTION ({ag['summary']}):\n    {body}", None
        return (f"{name} {status} without `DONE`/`QUESTION` in {Path(ag['summary'] or '-').name}: a swallowed "
                f"prompt (prompt --resend), a lost model (fallback) or a dialog:\n{screen(name, 10)}"), None
    line = f"{name} {status}: {_verdict_line(rnd, st, ag)}"
    if "missing" in line:
        line += "\n" + screen(name, 8)
    return line, None


def _poll(rnd: Round) -> tuple[list[str], list[str], bool]:
    events, submits, in_flight = [], [], False
    listed = agents_listed()
    live = {a["name"]: a for a in listed if a.get("name")}
    unnamed = {a.get("pane_id"): a for a in listed if not a.get("name")}
    now = time.time()
    with rnd.state() as st:
        for name, ag in st["agents"].items():
            if ag["status"] != "live":
                continue
            cur = live.get(name)
            orphan = unnamed.get(ag["pane"])
            if not cur and orphan and orphan.get("agent") in (ag["kind"], KINDS.get(ag["kind"], ("", ""))[1]):
                # herdr can drop a started agent's name (seen with codex behind its
                # hooks dialog) while the CLI keeps running in the pane: name it again.
                if "error" not in herdr("agent", "rename", ag["pane"], name):
                    cur = unnamed.pop(ag["pane"])
            if not cur:
                ag["status"] = "vanished"
                rnd.log("state", f"agent/{name}", status="failed", detail="vanished")
                events.append(f"{name} VANISHED ({ag['model']} via {ag['kind']}): restart {name}")
                continue
            s, seq = cur.get("agent_status"), cur.get("state_change_seq")
            if s in SETTLED or s in ("working", "blocked"):
                ag.pop("unknown_since", None)
            else:
                # herdr reads no state while a CLI sits on a screen its integration
                # does not cover (codex's hooks dialog): show that screen, keep the
                # agent in flight, and show it again only if the state stays unknown.
                if now - ag.setdefault("unknown_since", now) >= UNKNOWN_AFTER:
                    ag["unknown_since"] = now + 3 * UNKNOWN_AFTER
                    events.append(f"{name} BLOCKED ({ag['model']} via {ag['kind']}), no herdr state:\n{screen(name)}")
                in_flight = True
                continue
            if ag.get("pending") and s != "blocked":
                if s in SETTLED and not _prep_busy(st, ag["package"]):
                    _deliver(ag, cur, ag["pending"])
                in_flight = True
                continue
            if ag.get("sent_at"):
                # A CLI that is visibly working has picked the prompt up, even
                # when its integration has not bumped the state sequence yet.
                if seq == ag.get("sent_seq") and s in SETTLED:
                    if now - ag["sent_at"] < UNPICKED_AFTER:
                        in_flight = True
                        continue
                    ag["sent_at"] = None
                    events.append(f"{name} has not picked up its prompt after {UNPICKED_AFTER}s "
                                  f"(prompt {name} --resend, or read the screen):\n{screen(name, 8)}")
                    ag["reported_seq"] = seq
                    continue
                ag["sent_at"] = None
            if s in ("idle", "done", "blocked"):
                if seq != ag.get("reported_seq"):
                    ag["reported_seq"] = seq
                    text, pkg = _event_text(rnd, st, ag, s)
                    events.append(text)
                    if pkg:
                        submits.append(pkg)
            else:
                in_flight = True
        for cid, c in st["checks"].items():
            if c["status"] in ("queued", "running"):
                if c.get("pid") and not _alive(c["pid"]) and not Path(c["report"]).exists():
                    c["status"] = "DIED"
                else:
                    in_flight = True
                    continue
            if not c["reported"]:
                c["reported"] = True
                events.append(_check_result(rnd, cid, c))
    return events, submits, in_flight


def _settle_gates(rnd: Round) -> list[str]:
    """Accept every candidate whose two gates passed on the same sha; flag the failed ones once."""
    out = []
    st = rnd.read()
    keys = [k for k, p in st["packages"].items() if p["status"] == "open" and p["candidate"]]
    if st["merge"] and st["merge"].get("submitted") and st["merge"]["accepted"] != st["merge"]["candidate"]:
        keys.append("merge")
    for key in keys:
        pkg = _pkg(st, key)
        verdict, notes = _gates(st, key, pkg)
        if verdict == "pass":
            out.append(_accept(rnd, key))
        elif verdict == "fail" and pkg.get("flagged") != pkg["candidate"]:
            with rnd.state() as s2:
                _pkg(s2, key)["flagged"] = pkg["candidate"]
            out.append(f"{key}: both gates in, {'; '.join(notes)} -> send-back {key} (or drop)")
    return out


def cmd_wait(rnd: Round, a) -> None:
    deadline = time.time() + a.timeout
    while True:
        events, submits, in_flight = _poll(rnd)
        for key in submits:
            events.append(_submit(rnd, key))
            in_flight = True
        events += _settle_gates(rnd)
        if events or not in_flight or time.time() >= deadline:
            if not events:
                print("timeout: still working" if in_flight else "nothing in flight")
            if events:
                print("\n".join(events))
            print(_board(rnd.read()))
            return
        time.sleep(3)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _board(st: dict) -> str:
    live = agents_live()
    rows = []
    for key, p in list(st["packages"].items()) + ([("merge", st["merge"])] if st["merge"] else []):
        agents = [f"{n}:{live.get(n, {}).get('agent_status', 'gone')}" for n, ag in st["agents"].items()
                  if ag.get("package") == key and ag["status"] == "live"]
        checks = [c["status"] for c in st["checks"].values() if c["package"] == key]
        cycles = st.get("merge_cycles", 0) if key == "merge" else p["cycles"]
        rows.append(f"  {key}: {p['status'] if key != 'merge' else 'merge'} cand={short(p['candidate'])} "
                    f"acc={short(p['accepted'])} cycles={cycles} check={checks[-1] if checks else '-'}"
                    + (" " + " ".join(agents) if agents else ""))
    return "board:\n" + "\n".join(rows) if rows else "board: (no packages)"


def cmd_status(rnd: Round, a) -> None:
    st = rnd.read()
    print(f"round {st['slug']} base {short(st['base'])} repo {st['repo']}")
    for slot, p in st["active"].items():
        print(f"slot {slot}: " + (f"{p['model']} via {p['kind']}" if p else "none"))
    live = agents_live()
    for n, ag in st["agents"].items():
        if ag["status"] == "live":
            print(f"agent {n} ({ag['role']} {ag['package']}): {live.get(n, {}).get('agent_status', 'GONE')} "
                  f"on {ag['model']} via {ag['kind']}" + (f"; summary {ag['summary']}" if ag.get("summary") else ""))
    if st["merge"]:
        m = st["merge"]
        print(f"merge: {m['path']} merged={','.join(m['merged']) or '-'} order={','.join(m['order'])}"
              + (f" CONFLICT {m['conflict']['package']}" if m.get("conflict") else ""))
    print(_board(st))


# ----------------------------------------------------------------- merge ---

def cmd_merge(rnd: Round, a) -> None:
    st = rnd.read()
    if a.abort:
        return _merge_abort(rnd)
    if not st["merge"]:
        if not a.order:
            raise FleetError("first merge call needs --order")
        order = [s for s in a.order.split(",") if s]
        bad = [s for s in order if st["packages"].get(s, {}).get("status") != "accepted"]
        if bad:
            raise FleetError(f"not accepted: {', '.join(bad)}")
        branch = f"feat/{st['slug']}"
        m = _create_worktree(rnd, st, "merge", branch, f"{st['slug']}-merge", merge=True)
        m.update(order=order, merged=[], suite=a.suite, conflict=None, slot="slow",
                 review_from=st["base"], suite_passed=None)
        with rnd.state() as s:
            s["merge"] = m
        print(f"merge worktree {m['path']} on {branch} (pane {m['root_pane']})")
        if a.prep:
            print(f"prep queued ({_queue_check(rnd, 'merge', 'prep', None, a.prep)})")
        st = rnd.read()
    m = st["merge"]
    if a.suite:
        with rnd.state() as s:
            s["merge"]["suite"] = a.suite
        m["suite"] = a.suite
    path = m["path"]
    if m.get("conflict"):
        c = m["conflict"]
        if git(path, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False):
            print(f"merge of {c['package']} still unresolved; a merge implementer resolves it")
            return
        if m.get("accepted") != git(path, "rev-parse", "HEAD"):
            print(f"resolution of {c['package']} not accepted yet: submit merge, then accept merge")
            return
        with rnd.state() as s:
            s["merge"]["merged"].append(c["package"])
            s["merge"]["conflict"] = None
        m = rnd.read()["merge"]
    for slug in m["order"]:
        if slug in m["merged"]:
            continue
        pkg = st["packages"][slug]
        tip = git(st["repo"], "rev-parse", pkg["branch"])
        if tip != pkg["accepted"]:
            raise FleetError(f"feat/{slug} is at {short(tip)}, accepted {short(pkg['accepted'])}; stop and report")
        problem = _binding(path, git(path, "rev-parse", "HEAD"))
        if problem:
            raise FleetError(f"merge worktree: {problem}")
        pre = git(path, "rev-parse", "HEAD")
        msg = a.message.format(branch=pkg["branch"], target=f"feat/{st['slug']}")
        p = run(["git", "-C", path, "merge", "--no-ff", "-m", msg, pkg["branch"]])
        if p.returncode == 0:
            with rnd.state() as s:
                s["merge"]["merged"].append(slug)
                s["merge"]["accepted"] = s["merge"]["candidate"] = git(path, "rev-parse", "HEAD")
            print(f"merged {slug} ({short(git(path, 'rev-parse', 'HEAD'))})")
            continue
        files = git(path, "diff", "--name-only", "--diff-filter=U", check=False)
        if not git(path, "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False):
            raise FleetError(f"merge of {slug} failed without a conflict: {(p.stderr or p.stdout)[-300:]}")
        with rnd.state() as s:
            s["merge"]["conflict"] = {"package": slug, "pre": pre, "files": files.splitlines()}
            s["merge"]["review_from"] = pre
            s["merge"]["slot"] = st["packages"][slug].get("slot") if st["packages"][slug].get("slot") != "smol" else "default"
        print(f"CONFLICT merging {slug} (pre-merge {short(pre)}): {', '.join(files.splitlines())}\n"
              f"-> brief a merge implementer: implement merge --name {slug}-merge --brief FILE "
              f"(slot {rnd.read()['merge']['slot']}); then submit merge, accept merge, merge")
        return
    st = rnd.read()
    m = st["merge"]
    head = git(path, "rev-parse", "HEAD")
    print(f"all merged: feat/{st['slug']} at {short(head)}")
    if m.get("suite"):
        with rnd.state() as s:
            s["merge"]["candidate"] = head
            s["merge"]["accepted"] = head
        print(f"suite queued ({_queue_check(rnd, 'merge', 'suite', head, m['suite'])})")


def _merge_abort(rnd: Round) -> None:
    with rnd.state() as st:
        m = st["merge"]
        if not m or not m.get("conflict"):
            raise FleetError("no conflicted merge to abort")
        stops = _close_package_agents(rnd, st, "merge")
        c = m["conflict"]
        run(["git", "-C", m["path"], "merge", "--abort"])
        head = git(m["path"], "rev-parse", "HEAD")
        if head != c["pre"] or git(m["path"], "status", "--porcelain"):
            raise FleetError(f"after abort HEAD is {short(head)} (expected {short(c['pre'])}) or tree dirty; report it")
        st["packages"][c["package"]]["status"] = "conflict"
        rnd.log("state", f"package/{c['package']}/branch", status="retained",
                detail="merge conflict: " + ", ".join(c["files"]))
        m["stopped_at"] = c["package"]
        m["conflict"] = None
    print(f"aborted merge of {c['package']}; no later package merges this round. " + "; ".join(stops))


# --------------------------------------------------------------- cleanup ---

def cmd_cleanup(rnd: Round, a) -> None:
    st = rnd.read()
    running = [cid for cid, c in st["checks"].items() if c["status"] in ("queued", "running")
               and (not c.get("pid") or _alive(c["pid"]))]
    if running:
        raise FleetError("checks still running: " + ", ".join(running) + "; wait first")
    out = []
    with rnd.state() as st:
        for name, ag in st["agents"].items():
            if ag["status"] == "live":
                out.append(_stop_agent(rnd, st, name, close_pane=True))
        target = f"feat/{st['slug']}" if st["merge"] else None
        for slug, p in st["packages"].items():
            out.append(_cleanup_package(rnd, st, slug, p, target))
        if st["merge"]:
            out.append(_cleanup_merge(rnd, st, st["merge"]))
    _settle(rnd, "round/dir", "retained", "round closed; the directory is the round's record")
    print("\n".join(o for o in out if o))
    print(_report(rnd))


def _final(rnd: Round) -> dict[str, dict]:
    final = {}
    for line in Path(rnd.manifest).read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r["event"] in ("created", "state", "intent"):
                final[r["resource_key"]] = r
    return final


def _settle(rnd: Round, key: str, status: str, detail: str | None = None, **observed) -> None:
    """Record a disposition unless the resource already has exactly that one."""
    last = _final(rnd).get(key)
    if last and last.get("status") == status and not observed:
        return
    rnd.log("state", key, status=status, detail=detail, observed=observed or None)


def _settle_tree(rnd: Round, root: str, status: str, detail: str | None) -> None:
    """A worktree and every pane recorded under it share its fate (removal closes the workspace)."""
    for key, r in _final(rnd).items():
        if r.get("parent_key") == root and r.get("kind") == "pane" and r.get("status") in ("live", "retained"):
            _settle(rnd, key, status, detail)
    _settle(rnd, root, status, detail)


def _workspace_idle(ws: str) -> bool:
    panes = herdr("pane", "list", "--workspace", ws).get("result", {}).get("panes", [])
    return all(pane_idle(p["pane_id"]) for p in panes)


def _cleanup_package(rnd: Round, st: dict, slug: str, p: dict, target: str | None) -> str:
    wk, bk = f"package/{slug}/worktree", f"package/{slug}/branch"
    if p.get("cleaned"):
        return ""
    tip = git(st["repo"], "rev-parse", "-q", "--verify", p["branch"], check=False)
    reason = None
    if p["status"] != "accepted":
        reason = {"dropped": f"dropped: {p.get('drop_reason')}", "conflict": "merge conflict"}.get(
            p["status"], "not accepted")
    elif git(p["path"], "status", "--porcelain", check=False):
        reason = "uncommitted changes"
    elif tip != p["accepted"]:
        reason = f"branch moved to {short(tip)} after acceptance"
    elif not target or run(["git", "-C", st["repo"], "merge-base", "--is-ancestor", tip, target]).returncode:
        reason = "not merged"
    elif not _workspace_idle(p["workspace"]):
        reason = "a pane still runs something"
    p["cleaned"] = True
    if reason:
        _settle_tree(rnd, wk, "retained", reason)
        _settle(rnd, bk, "retained", reason)
        return f"{slug}: kept {p['path']} on {p['branch']} ({reason})"
    res = herdr("worktree", "remove", "--workspace", p["workspace"], "--force")
    if "error" in res:
        msg = res["error"].get("message")
        _settle_tree(rnd, wk, "retained", f"remove failed: {msg}")
        _settle(rnd, bk, "retained", "worktree kept")
        return f"{slug}: worktree remove failed ({msg}); kept"
    _settle_tree(rnd, wk, "removed", None)
    # `branch -d` judges merged-ness against the main checkout's HEAD, not the target; the
    # ancestry was proved above, so delete the ref only if it still points at the accepted sha.
    held = f"branch refs/heads/{p['branch']}" in git(st["repo"], "worktree", "list", "--porcelain", check=False)
    d = None if held else run(["git", "-C", st["repo"], "update-ref", "-d", f"refs/heads/{p['branch']}", p["accepted"]])
    if d is None or d.returncode:
        why = "checked out in another worktree" if held else d.stderr.strip()[-200:]
        _settle(rnd, bk, "retained", why)
        return f"{slug}: worktree removed; branch kept ({why})"
    _settle(rnd, bk, "removed")
    return f"{slug}: worktree and branch removed"


def _cleanup_merge(rnd: Round, st: dict, m: dict) -> str:
    if m.get("cleaned"):
        return ""
    m["cleaned"] = True
    head = git(m["path"], "rev-parse", "HEAD", check=False)
    green = any(c["package"] == "merge" and c["phase"] == "suite" and c["sha"] == head and c["status"] == "PASS"
                for c in st["checks"].values())
    reason = None
    if git(m["path"], "status", "--porcelain", check=False) or \
            git(m["path"], "rev-parse", "-q", "--verify", "MERGE_HEAD", check=False):
        reason = "uncommitted changes or a merge in progress"
    elif m.get("suite") and not green:
        reason = "suite not green on " + short(head)
    elif not _workspace_idle(m["workspace"]):
        reason = "a pane still runs something"
    _settle(rnd, "round/merge-target", "retained", "round output", sha=head)
    if reason:
        _settle_tree(rnd, "round/merge-worktree", "retained", reason)
        return f"merge worktree kept at {m['path']} ({reason}); {m['branch']} at {short(head)}"
    res = herdr("worktree", "remove", "--workspace", m["workspace"])
    if "error" in res:
        msg = res["error"].get("message")
        _settle_tree(rnd, "round/merge-worktree", "retained", f"remove refused: {msg}")
        return f"merge worktree kept at {m['path']} (remove refused: {msg})"
    _settle_tree(rnd, "round/merge-worktree", "removed", None)
    return f"merge worktree removed; {m['branch']} stays at {short(head)}"


def _report(rnd: Round) -> str:
    st = rnd.read()
    records = [json.loads(l) for l in Path(rnd.manifest).read_text().splitlines() if l.strip()]
    lines = ["report data:"]
    if st["merge"]:
        head = git(st["repo"], "rev-parse", "-q", "--verify", f"feat/{st['slug']}", check=False)
        suite = [c["status"] for c in st["checks"].values() if c["package"] == "merge" and c["phase"] == "suite"
                 and c["sha"] == head]
        lines.append(f"  merge target feat/{st['slug']} at {short(head)}; suite {suite[-1] if suite else 'not run'}; "
                     f"merged {','.join(st['merge']['merged']) or 'nothing'}")
        if not SHARED_BRANCHES.match(st["branch"]):
            lines.append(f"  for the user: git -C {st['repo']} merge --ff-only feat/{st['slug']} "
                         f"(fails if {st['branch']} moved past the base)")
    for slug, p in st["packages"].items():
        used = [f"{ag['model']} via {ag['kind']}" for ag in st["agents"].values()
                if ag.get("package") == slug and ag["role"] == "implementer"]
        revs = [f"{ag['model']}" for ag in st["agents"].values()
                if ag.get("package") == slug and ag["role"] != "implementer"]
        lines.append(f"  {slug}: {p['status']} slot {p['slot']} impl {', '.join(dict.fromkeys(used)) or '-'} "
                     f"review {', '.join(dict.fromkeys(revs)) or '-'} cycles {p['cycles']} acc {short(p['accepted'])}")
        for ag in st["agents"].values():
            if ag.get("package") == slug and ag["role"] == "reviewer" and ag.get("grades") == p["accepted"]:
                ok, v = validate_verdict(ag.get("verdict") or "", ag["grades"])
                if ok == "valid":
                    ac = v["assumption_check"]
                    lines.append(f"    assumption ({ac['status']}): {str(ac.get('assumption'))[:160]}")
    if st["merge"]:
        lines.append(f"  merge budget used {st.get('merge_cycles', 0)}/2")
    falls = [r for r in records if r["event"] == "slot" and (r.get("observed") or {}).get("replaced")]
    for r in falls:
        o = r["observed"]
        lines.append(f"  fallback {r['resource_key']}: {o['replaced'].get('model')} via "
                     f"{o['replaced'].get('provider_kind')} -> {o['model']} via {o['provider_kind']} ({r.get('detail')})")
    final = {}
    for r in records:
        if r["event"] in ("created", "state"):
            final[r["resource_key"]] = r
    kept = [f"{k} ({r.get('detail')})" for k, r in final.items() if r.get("status") == "retained"]
    open_ = [k for k, r in final.items() if r.get("status") in ("live", "planned") and r.get("kind") not in ("dir", "slot")]
    if kept:
        lines.append("  retained: " + "; ".join(kept))
    if open_:
        lines.append("  STILL OPEN: " + ", ".join(open_))
    lines.append(f"  round record: {rnd.dir}")
    return "\n".join(lines)


# ------------------------------------------------------------------ main ---

def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="fleet.py", description=__doc__.split("\n")[0])
    p.add_argument("--round")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init")
    s.add_argument("--repo", required=True)
    s.add_argument("--slug", required=True)
    s.add_argument("--slots")
    s = sub.add_parser("resolve")
    s.add_argument("--override", action="append", help="SLOT=model1,model2 for this round (repeatable)")
    s = sub.add_parser("package")
    s.add_argument("slug")
    s.add_argument("--slot", required=True)
    s.add_argument("--grade")
    s.add_argument("--prep")
    s.add_argument("--check")
    s.add_argument("--copy", action="append")
    s = sub.add_parser("implement")
    s.add_argument("package")
    s.add_argument("--brief", required=True)
    s.add_argument("--name")
    s.add_argument("--slot")
    s = sub.add_parser("prompt")
    s.add_argument("name")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--file")
    g.add_argument("--text")
    g.add_argument("--resend", action="store_true")
    for name in ("submit", "accept"):
        sub.add_parser(name).add_argument("package")
    s = sub.add_parser("send-back")
    s.add_argument("package")
    s.add_argument("--note")
    s.add_argument("--extend", action="store_true")
    s = sub.add_parser("drop")
    s.add_argument("package")
    s.add_argument("--reason", required=True)
    s = sub.add_parser("recheck")
    s.add_argument("package")
    s.add_argument("--prep", nargs="?", const="", help="rerun the prep (optionally with a corrected command)")
    s.add_argument("--copy", action="append")
    s.add_argument("--check", help="a corrected check command (the merge's suite)")
    s = sub.add_parser("adjudicate")
    s.add_argument("package")
    s.add_argument("--finding", required=True)
    s = sub.add_parser("wait")
    s.add_argument("--timeout", type=int, default=540)
    s = sub.add_parser("fallback")
    s.add_argument("name")
    s.add_argument("--reason", required=True)
    s.add_argument("--cli", action="store_true", help="the CLI itself failed (login, subscription), not one model")
    for name in ("restart", "stop"):
        sub.add_parser(name).add_argument("name")
    s = sub.add_parser("merge")
    s.add_argument("--order")
    s.add_argument("--prep")
    s.add_argument("--suite")
    s.add_argument("--abort", action="store_true")
    s.add_argument("--message", default="chore: merge {branch} into {target}")
    sub.add_parser("status")
    sub.add_parser("cleanup")
    s = sub.add_parser("_check")
    s.add_argument("cid")
    a = p.parse_args(argv)
    try:
        if a.cmd == "init":
            cmd_init(a)
            return 0
        if not a.round:
            raise FleetError("--round DIR is required (init printed it)")
        rnd = Round(a.round)
        handler = {"resolve": cmd_resolve, "package": cmd_package, "implement": cmd_implement,
                   "prompt": cmd_prompt, "submit": cmd_submit, "accept": cmd_accept, "send-back": cmd_send_back,
                   "drop": cmd_drop, "adjudicate": cmd_adjudicate, "recheck": cmd_recheck, "wait": cmd_wait, "fallback": cmd_fallback,
                   "restart": cmd_restart, "stop": cmd_stop, "merge": cmd_merge, "status": cmd_status,
                   "cleanup": cmd_cleanup, "_check": cmd_check_runner}[a.cmd]
        handler(rnd, a)
        return 0
    except (FleetError, ledger.LedgerError) as exc:
        print(f"fleet: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
