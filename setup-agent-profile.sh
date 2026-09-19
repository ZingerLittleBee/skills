#!/usr/bin/env bash
# Wire the shared agent profile into installed AI coding tools.
# Idempotent: safe to re-run anytime (e.g. after a tool update clobbers a link,
# or after editing agent-profile/AGENTS.md so the Cursor rule is regenerated).
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="$REPO_DIR/agent-profile/AGENTS.md"
CURSOR_RULE="$HOME/.cursor/rules/agent-profile.mdc"
GENERATED_MARKER="generated-by: setup-agent-profile.sh"

[[ -f "$PROFILE" ]] || { echo "error: $PROFILE not found" >&2; exit 1; }

# backup_if_regular <path>: move a non-symlink file aside; leave dest missing.
backup_if_regular() {
  local dst="$1"
  if [[ -e "$dst" && ! -L "$dst" ]]; then
    local bak
    bak="$dst.bak-$(date +%Y%m%d%H%M%S)"
    mv "$dst" "$bak"
    echo "  backed up regular file to $bak"
  fi
}

# link <target>: replace target with a symlink when its parent directory exists.
link() {
  local dst="$1"
  local dst_dir
  dst_dir="$(dirname "$dst")"
  if [[ ! -d "$dst_dir" ]]; then
    echo "  skipped $dst (parent directory not found)"
    return
  fi
  backup_if_regular "$dst"
  ln -sfn "$PROFILE" "$dst"
  echo "  $dst -> $PROFILE"
}

# Cursor CLI/editor do not read ~/.cursor/AGENTS.md. They load user-level
# file rules from ~/.cursor/rules/*.mdc (via the workspace-to-/ ancestor
# walk). AGENTS.md has no Cursor frontmatter, so this writes an always-apply
# .mdc that embeds the profile. Re-run this script after editing AGENTS.md.
install_cursor_rule() {
  local rule_dir
  rule_dir="$(dirname "$CURSOR_RULE")"
  if [[ ! -d "$rule_dir" ]]; then
    echo "  skipped $CURSOR_RULE (parent directory not found)"
    return
  fi
  if [[ -L "$CURSOR_RULE" ]]; then
    rm "$CURSOR_RULE"
  elif [[ -e "$CURSOR_RULE" ]] && ! grep -q "$GENERATED_MARKER" "$CURSOR_RULE"; then
    backup_if_regular "$CURSOR_RULE"
  fi
  {
    printf '%s\n' '---' 'alwaysApply: true' '---' '' \
      "<!-- $GENERATED_MARKER from agent-profile/AGENTS.md; do not edit -->" ''
    cat "$PROFILE"
  } > "$CURSOR_RULE"
  echo "  $CURSOR_RULE  (generated from $PROFILE)"
}

link "$HOME/.claude/CLAUDE.md"          # Claude Code
link "$HOME/.codex/AGENTS.md"           # Codex
link "$HOME/.omp/agent/AGENTS.md"       # Oh My Pi
link "$HOME/.config/opencode/AGENTS.md" # OpenCode
link "$HOME/.factory/AGENTS.md"         # Droid (Factory)
link "$HOME/.grok/AGENTS.md"            # Grok
link "$HOME/Library/Application Support/delta/AGENTS.md" # Delta
install_cursor_rule                     # Cursor (CLI + editor)

echo "Done. Configured tools pick up the profile on their next session."
