# skills

Personal collection of [agent skills](https://skills.sh/) for Claude Code and the
open agent-skills ecosystem. Each top-level directory is one skill.

## Install

Install a single skill with the Skills CLI:

```bash
npx skills add ZingerLittleBee/skills@<skill-name>
```

Add `-g` to install globally (user-level) and `-y` to skip confirmation prompts.

## Skills

| Skill | Description |
|---|---|
| [`implement-codex`](implement-codex/) | Implement a PRD or set of issues by delegating the coding to Codex (xhigh reasoning): Claude briefs, verifies, reviews, and commits. Invoke with `/implement-codex`. |
| [`testloop`](testloop/) | Drive a Claude ↔ Codex GUI test-fix loop: the main agent builds, installs, and launches the app and plans/judges/fixes, while Codex drives the running app via computer use to execute the test plan. Invoke with `/testloop [scope]`. |
| [`writing-x-zh-briefs`](writing-x-zh-briefs/) | Turn English X posts, AI news, product updates, or thin source material into concise Simplified Chinese X posts, quote-post takes, or one-to-two sentence commentary. |

### Examples

```bash
npx skills add ZingerLittleBee/skills@implement-codex
npx skills add ZingerLittleBee/skills@testloop
npx skills add ZingerLittleBee/skills@writing-x-zh-briefs
```
