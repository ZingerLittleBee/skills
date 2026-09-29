"""Fleet token usage from the CLIs' own session logs (diagnostic only).

claude and codex keep per-session logs keyed by working directory, so
agents working inside the attempt directory can be attributed exactly.
grok, agy and droid are reported as unavailable. Fleet usage is shown as
token counts (subscription billing), never converted to dollars.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from hfeval.config import HOME


def claude_slug(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def claude_usage(attempt_root: Path, exclude_sessions: set[str]) -> dict:
    prefix = claude_slug(attempt_root)
    total = {"sessions": 0, "input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0,
             "cache_creation_input_tokens": 0, "models": {}}
    for d in (HOME / ".claude" / "projects").glob(f"{prefix}*"):
        for f in d.glob("*.jsonl"):
            if f.stem in exclude_sessions:
                continue
            total["sessions"] += 1
            seen = set()
            for line in f.read_text(errors="replace").splitlines():
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = e.get("message") or {}
                if e.get("type") != "assistant" or not msg.get("usage") or msg.get("id") in seen:
                    continue
                seen.add(msg.get("id"))
                for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
                    total[k] += int(msg["usage"].get(k) or 0)
                m = msg.get("model", "?")
                total["models"][m] = total["models"].get(m, 0) + int(msg["usage"].get("output_tokens") or 0)
    return total


def codex_usage(codex_home: Path) -> dict:
    """Sum the last cumulative token count of every rollout in the attempt's CODEX_HOME."""
    total = {"sessions": 0, "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0,
             "reasoning_output_tokens": 0}
    for f in sorted((codex_home / "sessions").rglob("rollout-*.jsonl")):
        total["sessions"] += 1
        last = None
        for line in f.read_text(errors="replace").splitlines():
            if '"token_count"' in line:
                try:
                    last = json.loads(line)["payload"]["info"]["total_token_usage"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
        for k in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens"):
            total[k] += int((last or {}).get(k) or 0)
    return total


def fleet_usage(attempt_root: Path, codex_home: Path, orchestrator_session: str | None) -> dict:
    return {
        "claude": claude_usage(attempt_root, {orchestrator_session} if orchestrator_session else set()),
        "codex": codex_usage(codex_home),
        "unavailable": ["grok", "agy", "droid", "cursor"],
        "note": "token counts from CLI session logs; subscription-billed, not converted to dollars",
    }


def copy_orchestrator_session(repo: Path, session_id: str | None, dest: Path) -> Path | None:
    if not session_id:
        return None
    src = HOME / ".claude" / "projects" / claude_slug(repo) / f"{session_id}.jsonl"
    if not src.exists():
        return None
    shutil.copy(src, dest)
    return dest
