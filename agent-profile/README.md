# agent-profile

**Not a skill.** This directory is the single source of truth for the shared user-level agent profile (`AGENTS.md`), the global instructions for all AI coding CLI tools (Claude Code, Codex, OpenCode, Droid).

Everything outside this repo is a symlink. Edit `AGENTS.md` here, commit here; every tool picks up the change on its next session.

## Symlink layout

```
~/.claude/CLAUDE.md             ─┐
~/.codex/AGENTS.md               ├─> <repo>/agent-profile/AGENTS.md
~/.config/opencode/AGENTS.md     │
~/.factory/AGENTS.md            ─┘
```

## Setup

Clone this repo anywhere, then run:

```sh
./setup-agent-profile.sh
```

Idempotent; re-run it whenever a tool update replaces a symlink with a regular file (existing regular files are backed up, never overwritten). If the repo moves, re-run it from the new location.

## Rules of the road

- **Edit only in this repo**, then commit. Never edit the symlinked copies (changes would land in the repo file anyway, but uncommitted and easy to lose track of).
- **Keep the profile tool-agnostic.** Tool-specific quirks must be phrased conditionally ("if running inside a sandbox...") or live in that tool's own config.
- **Content must be in English** (matches the profile's own language rules for agent-instruction files).
- **Watch the size.** The profile is injected into every session of every tool; keep it around 2-3k tokens and cut low-value prose before adding new sections.
- The file is intentionally NOT at the repo root: agents working on this repo would otherwise load it as project-level instructions.

## History

Unified on 2026-07-15 from `~/.claude/CLAUDE.md`, `~/.claude/rules/{context7,git-commit}.md`, `~/.codex/AGENTS.md`, and `~/.config/opencode/AGENTS.md`, then moved into this repo as the canonical copy. Pre-unification originals are kept locally in `~/.agents/backup-2026-07-15/`.
