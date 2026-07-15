# agent-profile

**Not a skill.** This directory holds the shared user-level agent profile (`AGENTS.md`), the single source of truth for global instructions across all AI coding CLI tools (Claude Code, Codex, OpenCode, Droid).

It lives in this repo so it is version-controlled and portable across machines.

## Setup on a new machine

Clone this repo, then wire up the symlink chain:

```sh
# Local hub, all tools point here
mkdir -p ~/.agents
ln -sf "$(pwd)/agent-profile/AGENTS.md" ~/.agents/AGENTS.md

# Per-tool entry files
ln -sf ~/.agents/AGENTS.md ~/.claude/CLAUDE.md
ln -sf ~/.agents/AGENTS.md ~/.codex/AGENTS.md
ln -sf ~/.agents/AGENTS.md ~/.config/opencode/AGENTS.md
ln -sf ~/.agents/AGENTS.md ~/.factory/AGENTS.md
```

Run the commands from the repo root. Each tool picks up changes on its next session.

## Rules of the road

- Edit `agent-profile/AGENTS.md` in this repo only; never edit the symlinked copies.
- Keep the profile tool-agnostic. Tool-specific quirks must be phrased conditionally ("if running inside a sandbox...") or live in that tool's own config.
- The file is intentionally NOT at the repo root: agents working on this repo would otherwise load it as project-level instructions.
- If a tool update replaces a symlink with a regular file, re-run the `ln -sf` line for that tool.
