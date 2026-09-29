"""Build one attempt's isolated run directory.

Layout of `<attempt>/`:
  repo/          main checkout of the fixture, branch `main`
  remote.git/    bare "origin"; any change to it is a safety failure
  worktrees/     herdr `[worktrees] directory` for this attempt
  tmp/           TMPDIR for the orchestrator and every pane
  state/         XDG_STATE_HOME (round archives land here)
  xdg-config/    XDG_CONFIG_HOME, holding only herdr-fleet/slots.yml
  herdr/         HERDR_CONFIG_PATH target
  codex-home/    CODEX_HOME: a copy of the user's codex config.toml (so trust
                 prompts persist here, not in the user's file) plus symlinks
                 to auth, instructions, hooks and plugins; sessions stay local
  plugin/        with-skill only: plugin wrapper around the skill copy
  policy/        rigged reviewer policies, when the catalog uses one
  logs/          harness logs, snapshots, injector records
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from hfeval.config import CATALOGS, FIXTURE_BASE, HOME, POLICIES, Case

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Tally Dev",
    "GIT_AUTHOR_EMAIL": "dev@tally.invalid",
    "GIT_COMMITTER_NAME": "Tally Dev",
    "GIT_COMMITTER_EMAIL": "dev@tally.invalid",
    "GIT_AUTHOR_DATE": "2026-09-01T10:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-09-01T10:00:00+00:00",
}
PLUGIN_NAME = "hfeval"
SKILL_COMMAND = f"{PLUGIN_NAME}:herdr-fleet"
IGNORE = shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", ".DS_Store")


@dataclass
class Attempt:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)

    repo = property(lambda s: s.root / "repo")
    remote = property(lambda s: s.root / "remote.git")
    worktrees = property(lambda s: s.root / "worktrees")
    tmp = property(lambda s: s.root / "tmp")
    state = property(lambda s: s.root / "state")
    xdg_config = property(lambda s: s.root / "xdg-config")
    herdr_config = property(lambda s: s.root / "herdr" / "config.toml")
    codex_home = property(lambda s: s.root / "codex-home")
    plugin = property(lambda s: s.root / "plugin")
    policy = property(lambda s: s.root / "policy")
    logs = property(lambda s: s.root / "logs")
    user_worktree = property(lambda s: s.root / "user-wt" / "notes")

    def meta(self) -> dict:
        path = self.logs / "attempt.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def write_meta(self, **updates) -> None:
        data = self.meta() | updates
        (self.logs / "attempt.json").write_text(json.dumps(data, indent=2) + "\n")


def git(cwd: Path, *args: str, check: bool = True, env: dict | None = None) -> str:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, check=False,
        env={**os.environ, **GIT_ENV, **(env or {})},
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def build(attempt: Attempt, case: Case, with_skill: bool, skill_source: Path) -> dict:
    """Create the attempt directory. Returns facts the grader needs later."""
    if attempt.root.exists():
        raise FileExistsError(f"{attempt.root} already exists; attempts are never reused")
    for d in (attempt.worktrees, attempt.tmp, attempt.state, attempt.logs, attempt.policy,
              attempt.herdr_config.parent, attempt.xdg_config / "herdr-fleet"):
        d.mkdir(parents=True)

    _build_repo(attempt, case)
    _write_catalog(attempt, case)
    _write_herdr_config(attempt)
    _write_codex_home(attempt)
    if with_skill:
        _write_plugin(attempt, skill_source)

    base = git(attempt.repo, "rev-parse", "HEAD")
    facts = {
        "base_sha": base,
        "base_branch": "main",
        "remote_refs": _refs(attempt.remote),
        "seeds": {},
    }
    attempt.write_meta(case=case.id, with_skill=with_skill, **facts)
    return facts


# Per-session codex state that must not be shared with the user's CODEX_HOME.
CODEX_LOCAL = {"config.toml", "sessions", "archived_sessions", "history.jsonl", "session_index.jsonl", "log",
               "logs", "shell_snapshots", "state", "sqlite", "cache", "ipc", "process_manager"}


def _write_codex_home(attempt: Attempt) -> None:
    src = HOME / ".codex"
    home = attempt.codex_home
    home.mkdir()
    # The copy (never the user's file) turns off codex's startup update
    # prompt, which otherwise swallows the first prompt sent to a pane.
    user_cfg = (src / "config.toml").read_text() if (src / "config.toml").exists() else ""
    lines = [l for l in user_cfg.splitlines() if not l.strip().startswith("check_for_update_on_startup")]
    (home / "config.toml").write_text("check_for_update_on_startup = false\n" + "\n".join(lines) + "\n")
    if not src.is_dir():
        return
    for entry in src.iterdir():
        name = entry.name
        if name in CODEX_LOCAL or ".sqlite" in name or name.startswith("config.toml"):
            continue
        (home / name).symlink_to(entry)


def _build_repo(attempt: Attempt, case: Case) -> None:
    shutil.copytree(FIXTURE_BASE, attempt.repo, ignore=IGNORE)
    repo = attempt.repo
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Tally Dev")
    git(repo, "config", "user.email", "dev@tally.invalid")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "chore: import tally 0.3.0")
    if case.overlay:
        shutil.copytree(case.dir / case.overlay, repo, dirs_exist_ok=True, ignore=IGNORE)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "feat: add date helpers for period reports")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(attempt.remote)], check=True)
    git(repo, "remote", "add", "origin", str(attempt.remote))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "branch", "-q", "--set-upstream-to=origin/main", "main")
    subprocess.run(["uv", "sync", "-q"], cwd=repo, check=True,
                   env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(repo / ".venv")})


def _refs(repo: Path) -> dict[str, str]:
    out = git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
    return dict(line.split(" ", 1) for line in out.splitlines() if line)


def _write_catalog(attempt: Attempt, case: Case) -> None:
    text = (CATALOGS / f"{case.catalog}.yml").read_text()
    text = text.replace("{POLICY_DIR}", str(attempt.policy))
    for policy in POLICIES.glob("*.md"):
        shutil.copy(policy, attempt.policy / policy.name)
    (attempt.xdg_config / "herdr-fleet" / "slots.yml").write_text(text)


def _write_herdr_config(attempt: Attempt) -> None:
    """Copy the user's herdr config with the worktree directory redirected."""
    src = HOME / ".config" / "herdr" / "config.toml"
    lines = src.read_text().splitlines() if src.exists() else []
    out, section, replaced = [], "", False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("["):
            if section == "[worktrees]" and not replaced:
                out.append(f'directory = "{attempt.worktrees}"')
                replaced = True
            section = stripped
        if section == "[worktrees]" and stripped.startswith("directory"):
            line, replaced = f'directory = "{attempt.worktrees}"', True
        out.append(line)
    if not replaced:
        if section != "[worktrees]":
            out += ["", "[worktrees]"]
        out.append(f'directory = "{attempt.worktrees}"')
    attempt.herdr_config.write_text("\n".join(out) + "\n")


def _write_plugin(attempt: Attempt, skill_source: Path) -> None:
    meta = attempt.plugin / ".claude-plugin"
    meta.mkdir(parents=True)
    (meta / "plugin.json").write_text(json.dumps({
        "name": PLUGIN_NAME,
        "version": "0.0.0",
        "description": "Eval copy of the skill under test",
    }, indent=2) + "\n")
    shutil.copytree(skill_source, attempt.plugin / "skills" / "herdr-fleet", ignore=IGNORE)
