"""Dedicated named herdr session per attempt.

The eval never talks to the user's `default` session except for read-only
`workspace list` snapshots, and only ever stops or deletes sessions whose
name it created (prefix `hfeval-`).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from hfeval.config import EVAL_ROOT, HOME

SESSION_PREFIX = "hfeval-"
DEFAULT_SOCKET = HOME / ".config" / "herdr" / "herdr.sock"
SCRUBBED_ENV = ("GH_TOKEN", "GITHUB_TOKEN", "ANTHROPIC_API_KEY", "CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT",
                "CODEX_HOME")
# Prefixes of variables that belong to the session running the harness (its
# herdr pane, its Claude Code session and messaging socket), never the eval.
SCRUBBED_PREFIXES = ("HERDR_", "CLAUDE_CODE_", "UV_")


def session_dir(name: str) -> Path:
    return HOME / ".config" / "herdr" / "sessions" / name


def socket_path(name: str) -> Path:
    return session_dir(name) / "herdr.sock"


def base_env() -> dict[str, str]:
    """The user's environment minus secrets, herdr targeting and the harness's own venv."""
    env = {k: v for k, v in os.environ.items()
           if k not in SCRUBBED_ENV and k not in ("PWD", "OLDPWD", "VIRTUAL_ENV", "PYTHONPATH")
           and not k.startswith(SCRUBBED_PREFIXES)}
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                  if p and not p.startswith(str(EVAL_ROOT)))
    return env


def cli(socket: Path, *args: str, timeout: float = 30) -> dict:
    proc = subprocess.run(
        ["herdr", *args], capture_output=True, text=True, timeout=timeout,
        env={**base_env(), "HERDR_SOCKET_PATH": str(socket)},
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": {"code": "non_json", "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}}


class Session:
    def __init__(self, name: str):
        if not name.startswith(SESSION_PREFIX):
            raise ValueError(f"eval sessions must start with {SESSION_PREFIX!r}")
        self.name = name
        self.socket = socket_path(name)
        self.proc: subprocess.Popen | None = None

    def start(self, *, cwd: Path, profile: Path, env: dict[str, str], log: Path) -> None:
        if self.socket.exists() or self.name in list_sessions():
            raise RuntimeError(f"herdr session {self.name} already exists")
        with open(log, "ab") as out:
            self.proc = subprocess.Popen(
                ["sandbox-exec", "-f", str(profile), "herdr", "--session", self.name, "server"],
                cwd=cwd, env={**base_env(), **env}, stdout=out, stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        deadline = time.time() + 20
        while time.time() < deadline:
            if self.socket.exists() and "result" in self.call("workspace", "list"):
                return
            time.sleep(0.5)
        raise RuntimeError(f"herdr session {self.name} did not come up; see {log}")

    def call(self, *args: str, timeout: float = 30) -> dict:
        return cli(self.socket, *args, timeout=timeout)

    def snapshot(self) -> dict:
        return {
            "workspaces": self.call("workspace", "list").get("result", {}).get("workspaces", []),
            "agents": self.call("agent", "list").get("result", {}),
            "panes": self.call("pane", "list").get("result", {}),
        }

    def stop(self) -> None:
        subprocess.run(["herdr", "session", "stop", self.name], capture_output=True, env=base_env())
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        subprocess.run(["herdr", "session", "delete", self.name], capture_output=True, env=base_env())


def list_sessions() -> dict[str, str]:
    proc = subprocess.run(["herdr", "session", "list"], capture_output=True, text=True, env=base_env())
    out = {}
    for line in proc.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            out[parts[0]] = parts[1]
    return out


def default_session_fingerprint() -> list[dict]:
    """Read-only view of the user's default session, for before/after comparison."""
    if not DEFAULT_SOCKET.exists():
        return []
    spaces = cli(DEFAULT_SOCKET, "workspace", "list").get("result", {}).get("workspaces", [])
    return sorted(
        ({"id": w.get("workspace_id"), "label": w.get("label")} for w in spaces),
        key=lambda w: w["id"] or "",
    )


def integration_status() -> str:
    proc = subprocess.run(["herdr", "integration", "status"], capture_output=True, text=True, env=base_env())
    return proc.stdout
