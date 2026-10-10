# agent-profile

**Not a skill.** This directory is the single source of truth for the shared user-level agent profile (`AGENTS.md`), the global instructions for all AI coding tools (Claude Code, Codex, Amp, OpenCode, Droid, Grok, Delta, Cursor).

Everything outside this repo is a symlink, except Cursor (see below). Edit `AGENTS.md` here, commit here; symlink tools pick up the change on their next session. After editing, re-run `./setup-agent-profile.sh` so the Cursor rule is regenerated.

## Layout

```
~/.claude/CLAUDE.md             ─┐
~/.codex/AGENTS.md               │
~/.config/amp/AGENTS.md          │
~/.config/opencode/AGENTS.md     ├─> <repo>/agent-profile/AGENTS.md
~/.factory/AGENTS.md             │
~/.grok/AGENTS.md                │
~/Library/Application Support/delta/AGENTS.md ─┘

~/.cursor/rules/agent-profile.mdc   generated always-apply .mdc (not a symlink)
```

Cursor is not a symlink because Cursor CLI and the editor do **not** read `~/.cursor/AGENTS.md`. Their user-level file rules live in `~/.cursor/rules/*.mdc` and need `alwaysApply: true` frontmatter, which the shared `AGENTS.md` must not carry.

## Setup

Clone this repo anywhere, then run:

```sh
./setup-agent-profile.sh
```

Idempotent; re-run it whenever a tool update replaces a symlink with a regular file (existing regular files are backed up, never overwritten), after installing a supported tool, after editing `AGENTS.md` (Cursor copy), or if the repo moves. Targets whose parent directories do not exist are skipped with a notice.

## Rules of the road

- **Edit only in this repo**, then commit. Never edit the symlinked copies (changes would land in the repo file anyway, but uncommitted and easy to lose track of).
- **Keep the profile tool-agnostic.** Tool-specific quirks must be phrased conditionally ("if running inside a sandbox...") or live in that tool's own config.
- **Content must be in English** (matches the profile's own language rules for agent-instruction files).
- **Watch the size.** The profile is injected into every session of every tool; keep it around 2-3k tokens and cut low-value prose before adding new sections.
- The file is intentionally NOT at the repo root: agents working on this repo would otherwise load it as project-level instructions.

## History

Unified on 2026-07-15 from `~/.claude/CLAUDE.md`, `~/.claude/rules/{context7,git-commit}.md`, `~/.codex/AGENTS.md`, and `~/.config/opencode/AGENTS.md`, then moved into this repo as the canonical copy. Pre-unification originals are kept locally in `~/.agents/backup-2026-07-15/`.
