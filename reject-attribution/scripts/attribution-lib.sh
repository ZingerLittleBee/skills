# Shared attribution matchers for CI and Lefthook.
# Sourced by other scripts in this directory. Do not execute directly.
# Bash 3.2 compatible (macOS /bin/bash).

# Known coding-agent names. Keep in sync with check-pr-attribution usage.
ATTRIBUTION_AGENT_RE='Claude|Copilot|Cursor|Codex|OpenAI|Devin|Gemini|Jules|Windsurf|Cline|Aider|OpenCode|Codeium|Anthropic'

# Any email address. Domain must start with a letter so paths like icon@2x.png
# are not treated as addresses.
ATTRIBUTION_EMAIL_RE='[A-Za-z0-9._%+-]+@[A-Za-z][A-Za-z0-9.-]*\.[A-Za-z]{2,}'

ATTRIBUTION_CO_AUTHOR_RE='^[[:space:]]*Co-authored-by:'
ATTRIBUTION_AGENT_ADDRESSES='noreply@(anthropic\.com|cursor\.com|openai\.com|aider\.chat|opencode\.ai|kiro\.dev|augmentcode\.com|moonshot\.cn|moonshot\.ai|z\.ai|google\.com)|cursoragent@cursor\.com|codex@openai\.com|copilot@github\.com|aider@aider\.chat|amp@ampcode\.com|openhands@all-hands\.dev|kiro@amazon\.com|qwen-coder@alibabacloud\.com|junie@jetbrains\.com|junie@air\.dev|roomote@roocode\.com'
ATTRIBUTION_AGENT_GITHUB_ACCOUNTS='Copilot|copilot-swe-agent\[bot\]|claude\[bot\]|cursor\[bot\]|chatgpt-codex-connector\[bot\]|gemini-code-assist(\[bot\])?|gemini-cli|google-labs-jules\[bot\]|devin-ai-integration\[bot\]|coderabbitai(\[bot\])?|factory-droid\[bot\]|kiro-agent|roomote\[bot\]'
ATTRIBUTION_AGENT_NAMES='Copilot|Cursor|Codex|OpenAI|Anthropic|Gemini|Windsurf|Codeium|Aider|OpenCode|Amp|Augment|Qwen|GLM|Kimi Code|OpenHands|CodeRabbit|Roo Code|Claude[[:space:]]+(Code|Opus|Sonnet|Haiku|Fable)'
ATTRIBUTION_AGENT_CO_AUTHOR_RE="[<[:space:]](${ATTRIBUTION_AGENT_ADDRESSES})([>[:space:]]|$)|[<+](${ATTRIBUTION_AGENT_GITHUB_ACCOUNTS})@users\.noreply\.github\.com|Co-authored-by:[[:space:]]*(${ATTRIBUTION_AGENT_NAMES})([^A-Za-z]|$)"

attribution_agent_co_author_lines() {
  grep -iE "${ATTRIBUTION_CO_AUTHOR_RE}" | grep -iE "${ATTRIBUTION_AGENT_CO_AUTHOR_RE}" || true
}

attribution_email_lines() {
  grep -viE "${ATTRIBUTION_CO_AUTHOR_RE}" | grep -iE "${ATTRIBUTION_EMAIL_RE}" || true
}

# Print generated-by / made-with / assisted-by / robot-generated lines from
# stdin. Matches "generated/made with|by" plus a known agent name, or the
# signatures "🤖 Generated" and "Assisted-by:". Does not match "generate
# reports". Emails are handled separately by attribution_email_lines.
# Always exits 0.
attribution_generated_lines() {
  grep -iE \
    -e '🤖[[:space:]]*Generated' \
    -e 'Assisted-by:' \
    -e "Generated[[:space:]]+(with|by)[:[:space:]].*(${ATTRIBUTION_AGENT_RE})" \
    -e "Generated-(with|by)[:[:space:]]*(${ATTRIBUTION_AGENT_RE})" \
    -e "Made[[:space:]]+with[:[:space:]].*(${ATTRIBUTION_AGENT_RE})" \
    -e "Made-with[:[:space:]]*(${ATTRIBUTION_AGENT_RE})" \
    || true
}
