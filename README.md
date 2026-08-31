# skills

Personal collection of [agent skills](https://skills.sh/) for Claude Code and the
open agent-skills ecosystem. Each top-level directory is one skill, except
[`agent-profile/`](agent-profile/) which holds the shared agent profile and
[`goals/`](goals/) which holds reference-only Codex goal drafts (see below).

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
| [`publish-release`](publish-release/) | The release convention: unreleased work accumulates under CHANGELOG's `[Unreleased]` heading, and one `make publish` (options as make variables: `VERSION=`, `DRY_RUN=1`, `YES=1`) cuts it — renaming the section, updating each declared version file, regenerating the derived ones by command, tagging, and releasing via GitHub Actions or a local build. Prints the whole plan and asks before mutating anything. |
| [`herdr-fleet`](herdr-fleet/) | Run one round of parallel implementation across multiple CLI coding agents (claude, codex, droid, grok, …) in herdr-managed git worktrees: the orchestrator packages the backlog, assigns each package to an agent kind by difficulty, watches progress, grades fixed commits with Herdr reviewer agents, validates serially, merges accepted packages onto one local branch, and removes only clean merged worktrees. Invoke with `/herdr-fleet`. |
| [`implement-codex`](implement-codex/) | Implement a PRD or set of issues by delegating the coding to Codex (`gpt-5.6-sol`, xhigh reasoning): Claude briefs, verifies, reviews, and commits. Invoke with `/implement-codex`. |
| [`testloop`](testloop/) | Run a host-agnostic GUI test-fix loop through Herdr with a `gpt-5.6-terra` Codex tester: the current agent builds, installs, launches, judges, and fixes, while Codex drives the app via computer use. Requires a Herdr-managed pane. Invoke it explicitly with the host's skill syntax; an optional scope can narrow the run. |
| [`ui-research`](ui-research/) | Research how excellent products design and implement a piece of UI (visual references, motion, implementation, principles) and present an evidence-backed local HTML report with screenshots; greps the current repo before recommending anything. Triggers automatically on UI-research-shaped requests. |
| [`unslop`](unslop/) | Humanize English or Chinese prose when explicitly requested. Removes formulaic AI writing patterns while preserving facts, intent, technical language, quotations, and regional Chinese usage. |
| [`writing-x-zh-briefs`](writing-x-zh-briefs/) | Turn English X posts, AI news, product updates, or thin source material into concise Simplified Chinese X posts, quote-post takes, or one-to-two sentence commentary. |

### Examples

```bash
npx skills add ZingerLittleBee/skills@dispatch-tickets
npx skills add ZingerLittleBee/skills@herdr-fleet
npx skills add ZingerLittleBee/skills@implement-codex
npx skills add ZingerLittleBee/skills@publish-release
npx skills add ZingerLittleBee/skills@testloop
npx skills add ZingerLittleBee/skills@ui-research
npx skills add ZingerLittleBee/skills@unslop
npx skills add ZingerLittleBee/skills@writing-x-zh-briefs
```

## Agent profile

[`agent-profile/AGENTS.md`](agent-profile/AGENTS.md) is the user-level agent profile
shared across Claude Code, Codex, OpenCode, Droid, Grok, and Cursor. It is not a
skill; it is version-controlled here and wired into each tool by
[`./setup-agent-profile.sh`](setup-agent-profile.sh) (symlinks for most tools; a
generated always-apply `.mdc` for Cursor). On a new machine, clone this repo and
run that script; see [`agent-profile/README.md`](agent-profile/README.md) for details.

## Goals

[`goals/`](goals/) is a reference library for long-running Codex goal drafts. It
is not installed, loaded automatically, or exposed as a quick invocation. Open a
goal and copy its contents manually when needed; see
[`goals/README.md`](goals/README.md).
