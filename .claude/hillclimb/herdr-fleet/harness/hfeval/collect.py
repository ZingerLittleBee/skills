"""Before/after state snapshots for one attempt."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from hfeval.config import HOME, SKILL_SOURCE
from hfeval.fixture import Attempt, git
from hfeval.herdr import Session, default_session_fingerprint, integration_status
from hfeval.sandbox import PROTECTED_FILES

WATCHED_FILES = [
    *PROTECTED_FILES,
    HOME / ".config" / "herdr" / "config.toml",
    HOME / ".config" / "herdr-fleet" / "slots.yml",
    HOME / ".agents" / "skills" / "herdr-fleet" / "SKILL.md",
    SKILL_SOURCE / "SKILL.md",
]


def _hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _refs(repo: Path) -> dict[str, str]:
    out = git(repo, "for-each-ref", "--format=%(refname) %(objectname)", check=False)
    return dict(line.split(" ", 1) for line in out.splitlines() if " " in line)


def _worktrees(repo: Path) -> list[dict]:
    out = git(repo, "worktree", "list", "--porcelain", check=False)
    items, cur = [], {}
    for line in out.splitlines() + [""]:
        if not line:
            if cur:
                items.append(cur)
            cur = {}
            continue
        key, _, value = line.partition(" ")
        cur[key] = value or True
    return items


def _in_progress(repo: Path) -> list[str]:
    gitdir = Path(git(repo, "rev-parse", "--absolute-git-dir", check=False) or repo / ".git")
    return [n for n in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")
            if (gitdir / n).exists()]


def _reflogs(repo: Path) -> dict[str, list[str]]:
    """All reflogs of the repo, including per-worktree HEAD logs."""
    gitdir = repo / ".git"
    logs = {}
    for f in [*(gitdir / "logs").rglob("*"), *(gitdir / "worktrees").glob("*/logs/HEAD")]:
        if f.is_file():
            logs[str(f.relative_to(gitdir))] = f.read_text(errors="replace").splitlines()
    return logs


def snapshot(attempt: Attempt, session: Session | None) -> dict:
    repo = attempt.repo
    seeds = attempt.meta().get("seeds", {})
    snap = {
        "head_ref": git(repo, "symbolic-ref", "-q", "HEAD", check=False) or "DETACHED",
        "head_sha": git(repo, "rev-parse", "HEAD", check=False),
        "status": git(repo, "status", "--porcelain=v1", "--untracked-files=all", check=False).splitlines(),
        "in_progress": _in_progress(repo),
        "refs": _refs(repo),
        "remotes": git(repo, "remote", "-v", check=False).splitlines(),
        "local_config": git(repo, "config", "--local", "--list", check=False).splitlines(),
        "worktrees": _worktrees(repo),
        "reflogs": _reflogs(repo),
        "remote_refs": _refs(attempt.remote),
        "readme_sha": _hash(repo / "README.md"),
        "seeded_files": {p: _hash(Path(p)) for p in seeds.get("files", {})},
        "seeded_worktrees": [
            {**w, "exists": Path(w["path"]).exists(),
             "now_head": git(Path(w["path"]), "rev-parse", "HEAD", check=False) if Path(w["path"]).exists() else "",
             "now_status": git(Path(w["path"]), "status", "--porcelain", check=False).splitlines()
             if Path(w["path"]).exists() else []}
            for w in seeds.get("worktrees", [])
        ],
        "seeded_round_dirs": {d: (Path(d) / "manifest.jsonl").read_text() if (Path(d) / "manifest.jsonl").exists() else None
                              for d in seeds.get("round_dirs", [])},
        "watched_files": {str(p): _hash(p) for p in WATCHED_FILES},
        "default_session": default_session_fingerprint(),
        "integration_status": integration_status(),
        "herdr": session.snapshot() if session else {},
        "user_state_dirs": sorted(p.name for p in (HOME / ".local" / "state" / "herdr-fleet").glob("*"))
        if (HOME / ".local" / "state" / "herdr-fleet").exists() else [],
    }
    return snap


def save(attempt: Attempt, name: str, snap: dict) -> Path:
    path = attempt.logs / f"snapshot-{name}.json"
    path.write_text(json.dumps(snap, indent=1, default=str))
    return path


def process_tree_alive(pattern: str) -> list[str]:
    proc = subprocess.run(["pgrep", "-fl", pattern], capture_output=True, text=True)
    return proc.stdout.splitlines()
