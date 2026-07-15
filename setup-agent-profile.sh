#!/usr/bin/env bash
# Wire the shared agent profile into every AI coding CLI tool via symlinks.
# Idempotent: safe to re-run anytime (e.g. after a tool update clobbers a link).
# Each tool entry links directly to <this repo>/agent-profile/AGENTS.md.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROFILE="$REPO_DIR/agent-profile/AGENTS.md"

[[ -f "$PROFILE" ]] || { echo "error: $PROFILE not found" >&2; exit 1; }

# link <target>: replace target with a symlink to the profile, backing up any regular file
link() {
  local dst="$1"
  mkdir -p "$(dirname "$dst")"
  if [[ -e "$dst" && ! -L "$dst" ]]; then
    local bak="$dst.bak-$(date +%Y%m%d%H%M%S)"
    mv "$dst" "$bak"
    echo "  backed up regular file to $bak"
  fi
  ln -sfn "$PROFILE" "$dst"
  echo "  $dst -> $PROFILE"
}

link "$HOME/.claude/CLAUDE.md"          # Claude Code
link "$HOME/.codex/AGENTS.md"           # Codex
link "$HOME/.config/opencode/AGENTS.md" # OpenCode
link "$HOME/.factory/AGENTS.md"         # Droid (Factory)

echo "Done. Tools pick up the profile on their next session."
