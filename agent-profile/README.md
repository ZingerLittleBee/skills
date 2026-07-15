# agent-profile

**Not a skill.** This directory is the single source of truth for the shared user-level agent profile (`AGENTS.md`), the global instructions for all AI coding CLI tools (Claude Code, Codex, OpenCode, Droid).

Everything outside this repo is a symlink. Edit `AGENTS.md` here, commit here; every tool picks up the change on its next session.

## Symlink chain

```
~/.claude/CLAUDE.md             ─┐
~/.codex/AGENTS.md               ├─> ~/.agents/AGENTS.md ─> <repo>/agent-profile/AGENTS.md
~/.config/opencode/AGENTS.md     │   ~/.agents/README.md ─> <repo>/agent-profile/README.md
~/.factory/AGENTS.md            ─┘
```

`~/.agents/` is the local hub: tools point at it, it points into this repo. The extra hop means a repo move only requires fixing two links instead of four.

## Setup on a new machine

Clone this repo, then run from the repo root:

```sh
# Local hub
mkdir -p ~/.agents
ln -sf "$(pwd)/agent-profile/AGENTS.md" ~/.agents/AGENTS.md
ln -sf "$(pwd)/agent-profile/README.md" ~/.agents/README.md

# Per-tool entry files
ln -sf ~/.agents/AGENTS.md ~/.claude/CLAUDE.md
ln -sf ~/.agents/AGENTS.md ~/.codex/AGENTS.md
ln -sf ~/.agents/AGENTS.md ~/.config/opencode/AGENTS.md
ln -sf ~/.agents/AGENTS.md ~/.factory/AGENTS.md
```

## Rules of the road

- **Edit only in this repo**, then commit. Never edit the symlinked copies (changes would land in the repo file anyway, but uncommitted and easy to lose track of).
- **Keep the profile tool-agnostic.** Tool-specific quirks must be phrased conditionally ("if running inside a sandbox...") or live in that tool's own config.
- **Content must be in English** (matches the profile's own language rules for agent-instruction files).
- **Watch the size.** The profile is injected into every session of every tool; keep it around 2-3k tokens and cut low-value prose before adding new sections.
- The file is intentionally NOT at the repo root: agents working on this repo would otherwise load it as project-level instructions.
- If a tool update replaces a symlink with a regular file, re-run the matching `ln -sf` line above.

## History

Unified on 2026-07-15 from `~/.claude/CLAUDE.md`, `~/.claude/rules/{context7,git-commit}.md`, `~/.codex/AGENTS.md`, and `~/.config/opencode/AGENTS.md`, then moved into this repo as the canonical copy. Pre-unification originals are kept locally in `~/.agents/backup-2026-07-15/`.
