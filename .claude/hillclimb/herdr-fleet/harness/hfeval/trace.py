"""Convert `claude -p --output-format stream-json` logs into report turns.

Output turns follow the eval report contract: `{role, content, thinking?,
name?}` with role in system | user | assistant | tool_call | tool_result.
Also extracts the tool calls the graders inspect.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

MAX_RESULT_CHARS = 20000


@dataclass
class ToolCall:
    turn: int
    name: str
    input: dict
    result: str = ""
    is_error: bool = False


@dataclass
class OrchestratorTrace:
    turns: list[dict] = field(default_factory=list)
    calls: list[ToolCall] = field(default_factory=list)
    model: str | None = None
    models: dict = field(default_factory=dict)   # modelUsage from result events, merged
    usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0,
                                                 "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})
    cost_usd: float = 0.0
    final_text: str = ""
    skills_loaded: list[str] = field(default_factory=list)
    stop_reason: str | None = None


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return json.dumps(content)


def parse(logs: list[Path], user_messages: list[str]) -> OrchestratorTrace:
    tr = OrchestratorTrace()
    pending: dict[str, ToolCall] = {}
    for turn, log in enumerate(logs):
        events = []
        for line in log.read_text().splitlines() if log.exists() else []:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if turn < len(user_messages):
            tr.turns.append({"role": "user", "content": user_messages[turn]})
        for e in events:
            et = e.get("type")
            if et == "system" and e.get("subtype") == "init":
                tr.model = tr.model or e.get("model")
                if turn == 0:
                    tr.turns.insert(0, {"role": "system", "content": (
                        f"claude -p session {e.get('session_id')}\nmodel: {e.get('model')}\n"
                        f"permission mode: {e.get('permissionMode')}\ncwd: {e.get('cwd')}\n"
                        f"tools: {', '.join(e.get('tools', []))}\n"
                        f"slash commands/skills: {', '.join(e.get('slash_commands', []) or [])}")})
            elif et == "assistant":
                msg = e.get("message", {})
                thinking = ""
                for c in msg.get("content", []):
                    ct = c.get("type")
                    if ct == "thinking":
                        thinking += c.get("thinking", "")
                    elif ct == "text" and c.get("text", "").strip():
                        turn_d = {"role": "assistant", "content": c["text"]}
                        if thinking:
                            turn_d["thinking"], thinking = thinking, ""
                        tr.turns.append(turn_d)
                    elif ct == "tool_use":
                        call = ToolCall(turn=turn, name=c.get("name", ""), input=c.get("input") or {})
                        pending[c.get("id")] = call
                        tr.calls.append(call)
                        if call.name == "Skill":
                            tr.skills_loaded.append(str(call.input.get("skill") or call.input.get("command")))
                        turn_d = {"role": "tool_call", "name": call.name,
                                  "content": json.dumps(call.input, indent=2, ensure_ascii=False)}
                        if thinking:
                            turn_d["thinking"], thinking = thinking, ""
                        tr.turns.append(turn_d)
            elif et == "user":
                for c in e.get("message", {}).get("content", []) if isinstance(e.get("message", {}).get("content"), list) else []:
                    if c.get("type") == "tool_result":
                        text = _text(c.get("content"))
                        call = pending.pop(c.get("tool_use_id"), None)
                        if call:
                            call.result, call.is_error = text, bool(c.get("is_error"))
                        shown = text if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + f"\n[... {len(text) - MAX_RESULT_CHARS} chars truncated in trace]"
                        tr.turns.append({"role": "tool_result", "content": shown})
                    elif c.get("type") == "text" and turn == 0 and "herdr-fleet" in c.get("text", "")[:200]:
                        # Expanded slash-command body: record that the skill loaded.
                        tr.skills_loaded.append("herdr-fleet (slash command)")
            elif et == "result":
                tr.final_text = e.get("result") or tr.final_text
                tr.cost_usd += float(e.get("total_cost_usd") or 0.0)
                tr.stop_reason = e.get("subtype")
                for k in tr.usage:
                    tr.usage[k] += int((e.get("usage") or {}).get(k) or 0)
                for m, u in (e.get("modelUsage") or {}).items():
                    agg = tr.models.setdefault(m, {})
                    for k, v in u.items():
                        if isinstance(v, (int, float)):
                            agg[k] = agg.get(k, 0) + v
    return tr


def bash_commands(tr: OrchestratorTrace) -> list[str]:
    return [str(c.input.get("command", "")) for c in tr.calls if c.name == "Bash"]
