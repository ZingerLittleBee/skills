#!/usr/bin/env bash
# Install the skills I use globally, straight from their upstream repos.
# Idempotent: safe to re-run anytime; each run fetches the latest upstream version.
# Works from a clone or piped from GitHub (e.g. on a fresh VM):
#   curl -fsSL https://raw.githubusercontent.com/ZingerLittleBee/skills/main/install-skills.sh | bash
# Override the target agents with SKILLS_AGENTS="claude-code codex".
set -euo pipefail

# Without -a, the Skills CLI links into every agent it knows (60+ dot
# directories on a fresh machine), so the target agents are always explicit.
AGENTS="${SKILLS_AGENTS:-claude-code codex amp cursor droid opencode gemini-cli github-copilot cline kilo kimi-code-cli pi warp zed}"

# One entry per source repo: "<owner/repo> <skill>...". Keep in sync with README.md.
SOURCES=(
  "mattpocock/skills ask-matt code-review codebase-design diagnosing-bugs domain-modeling grill-me grill-with-docs grilling handoff implement implement-spec improve-codebase-architecture prototype research retro setup-matt-pocock-skills tdd teach to-questionnaire to-spec to-tickets triage wait-what wayfinder wizard writing-for-agents"
  "jakubkrehel/skills better-accessibility better-colors better-interface better-layout better-typography better-ui better-writing state-machine"
  "emilkowalski/skills animation-vocabulary apple-design emil-design-eng find-animation-opportunities improve-animations pick-ui-library review-animations"
  "ZingerLittleBee/skills dispatch-tickets herdr-fleet publish-release reject-attribution testloop ui-research unslop"
  "vercel-labs/skills find-skills"
  "vercel-labs/agent-skills vercel-react-best-practices web-design-guidelines"
  "vercel-labs/agent-browser agent-browser"
  "wheresryan22/anatomy anatomy"
  "leonxlnx/taste-skill design-taste-frontend"
  "herdrdev/herdr herdr"
  "shadcn/improve improve"
  "humanlayer/skills show-me"
)

command -v npx >/dev/null || { echo "error: npx not found; install Node.js first" >&2; exit 1; }

failed=()
for entry in "${SOURCES[@]}"; do
  read -r repo skills <<<"$entry"
  echo "==> $repo"
  # stdin from /dev/null: under `curl | bash` the script itself is on stdin.
  # shellcheck disable=SC2086 # AGENTS and skills are intentionally word-split
  if ! npx -y skills add "$repo" -g -y -a $AGENTS -s $skills </dev/null; then
    failed+=("$repo")
  fi
done

if ((${#failed[@]})); then
  echo "error: failed to install from: ${failed[*]}" >&2
  exit 1
fi
echo "Installed skills for: $AGENTS"
