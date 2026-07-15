# skills

Personal collection of [agent skills](https://skills.sh/) for Claude Code and the
open agent-skills ecosystem. Each top-level directory is one skill, except
[`agent-profile/`](agent-profile/) which holds the shared agent profile (see below).

## Install

Install a single skill with the Skills CLI:

```bash
npx skills add ZingerLittleBee/skills@<skill-name>
```

Add `-g` to install globally (user-level) and `-y` to skip confirmation prompts.

## Skills

| Skill | Description |
|---|---|
| [`dispatch-tickets`](dispatch-tickets/) | Run a set of tracker tickets to completion in one session: a dispatcher main agent spawns a fresh implementer subagent per ticket in dependency order, verifies each result, and closes tickets; simple tickets go to a cheaper model. Invoke with `/dispatch-tickets #N #N …` or `parent=#N`. |
| [`implement-codex`](implement-codex/) | Implement a PRD or set of issues by delegating the coding to Codex (`gpt-5.6-sol`, xhigh reasoning): Claude briefs, verifies, reviews, and commits. Invoke with `/implement-codex`. |
| [`testloop`](testloop/) | Drive a Claude ↔ Codex GUI test-fix loop with `gpt-5.6-terra`: the main agent builds, installs, and launches the app and plans/judges/fixes, while Codex drives the running app via computer use to execute the test plan. Invoke with `/testloop [scope]`. |
| [`writing-x-zh-briefs`](writing-x-zh-briefs/) | Turn English X posts, AI news, product updates, or thin source material into concise Simplified Chinese X posts, quote-post takes, or one-to-two sentence commentary. |

### Examples

```bash
npx skills add ZingerLittleBee/skills@dispatch-tickets
npx skills add ZingerLittleBee/skills@implement-codex
npx skills add ZingerLittleBee/skills@testloop
npx skills add ZingerLittleBee/skills@writing-x-zh-briefs
```

## Agent profile

[`agent-profile/AGENTS.md`](agent-profile/AGENTS.md) is the user-level agent profile
shared across Claude Code, Codex, OpenCode, and Droid. It is not a skill; it is
version-controlled here and wired into each tool via symlinks. On a new machine,
clone this repo and run [`./setup-agent-profile.sh`](setup-agent-profile.sh); see
[`agent-profile/README.md`](agent-profile/README.md) for details.
