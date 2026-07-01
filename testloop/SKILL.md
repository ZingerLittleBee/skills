---
name: testloop
description: Drive the Claude<->Codex test-fix loop interactively from this session. You (Claude) plan the tests, judge the results, and fix the bugs — all visible here — while Codex runs the tests against the app via computer use. Invoke with `/testloop [scope]`, e.g. `/testloop login flow`.
disable-model-invocation: true
---

# testloop — interactive test-fix loop

You are the **driver** of a Claude ↔ Codex loop. There is no separate program:
this skill *is* testloop. You do the mechanical steps yourself with the Bash and
file tools — write templates, run Codex, snapshot rounds — right here where the
user can watch.

The split of responsibilities is:

- **You (main agent):** own the **app lifecycle and the reasoning** — you
  **build, install, and launch** the app, write the test plan, run Codex to drive
  it, wait for results, then decide **fix vs. adjust**, re-test, and **quit** the
  app. Building, planning, judging, and fixing all happen here, in the open,
  where the user can watch and steer.
- **Codex:** the **hands** — it drives the **already-running** app via computer
  use to execute your test plan, and writes the results. It does NOT build,
  install, launch, or quit the app; you do.

This split exists because the two halves need different powers:
**building/installing/launching needs unsandboxed host access** (writing
`/Applications`, `open`, `ps` — which you, the main agent, have via Bash), while
**driving the GUI needs computer use** (which Codex has). Each does only the part
it is uniquely able to do.

The optional argument after `/testloop` is the **scope** to focus this run
(e.g. `login flow`, `settings sync`). No argument = test broadly.

## Golden rules

- **Respect the project's own instructions.** Read `CLAUDE.md`, `AGENTS.md`, and
  `.testloop/project.md` before planning, and follow them (build/test commands,
  conventions, gotchas). They override anything here.
- **Everything is visible.** Don't hide reasoning in a subagent. State your plan,
  your verdict, and your fixes in the conversation.
- **When you genuinely cannot decide, stop and ask the user** — don't guess. This
  applies to ambiguous requirements, risky fixes, and unclear test results.
- **Minimal fixes only.** Fix the failing behavior; don't refactor or add scope.
  Never edit the test plan to make a failure "pass".

## Setup (first run in a project)

`.testloop/config.yaml` (build command, `codex_cmd`, `max_rounds`) and
`.testloop/project.md` (the project profile used as shared context) are the
loop's inputs. If they're missing, **fill them in yourself** — you are already a
Claude session, so inspect the project and write the real values, in the open,
where the user can watch.

1. If `.testloop/config.yaml` is missing, scaffold it and the profile from the
   [templates below](#templates) — write them verbatim, then replace the
   placeholders. Create the dir first: `mkdir -p .testloop`.
2. Inspect the project **yourself** — directory layout, `package.json` scripts,
   `tauri.conf.json` / `Cargo.toml` / vite / next config, `CLAUDE.md`,
   `AGENTS.md` — and edit the two files with real values:
   - `config.yaml`: real `build_cmd`, `target_kind` (`web` / `desktop` /
     `mobile`), `target_desc`, `codex_cmd`, `max_rounds`.
   - `project.md`: overview, structure, how to launch, how to test, gotchas.
3. **Show the user the filled-in `config.yaml` and confirm** the `build_cmd` and
   `codex_cmd` before continuing.

If the files already exist, skip straight to the loop after reading `CLAUDE.md`,
`AGENTS.md`, and `.testloop/config.yaml` + `.testloop/project.md` for context.

### Desktop apps — install a real build, don't use a dev server

For `target_kind: desktop`, Codex drives the app through the OS as a normally
**installed application**. So `build_cmd` must produce a real, installed app that
**you** then launch — do NOT point it at a dev server (`pnpm tauri dev`,
`npm start`, an Electron dev window, etc.), because computer use can't reliably
target a transient dev process.

The build command depends on the toolchain, so **inspect the project and
decide** — it may be Tauri, Electron, Flutter, native, or a custom bundler
script. Its job is to **build a debug/local bundle and install it into the
platform's app location**. Read `package.json` scripts and the bundler config,
prefer the debug/unsigned build (faster, fine for local testing), and **confirm
the resulting `build_cmd` with the user** before running.

You (the main agent) run `build_cmd`, then launch and later quit the installed
app yourself; Codex only drives it while it is running. On macOS that means
installing the `.app` into `/Applications`, launching with `open -a "<AppName>"`,
and quitting with `osascript -e 'quit app "<AppName>"'` (derive `<AppName>` from
`target_desc` / `project.md`). For example, a Tauri project's `build_cmd`
typically looks like:

```yaml
build_cmd: >-
  pnpm tauri build --debug &&
  rm -rf "/Applications/<AppName>.app" &&
  cp -R "src-tauri/target/debug/bundle/macos/<AppName>.app" /Applications/
```

— but an Electron app, a custom bundler script (e.g. a `universal` / `package`
npm script), signing, or notarization can change both the build command and the
output path. Treat the Tauri snippet as an illustration, not a default.

## The loop

Read `.testloop/config.yaml` for `build_cmd`, `target_kind`, `target_desc`,
`codex_cmd`, `repo_dir`, and `max_rounds`. Repeat up to `max_rounds` (default 8).
Track the round number `N`, starting at 1. Announce each round:
`Round N — <scope or "broad">`.

**Codex is stateless across rounds — by design.** Each round runs a fresh
`codex exec` (no session resume) and the app is rebuilt and relaunched, so Codex
starts clean every time. That is deliberate: it keeps re-verification independent
(Codex is not biased by a bug it "remembers" failing) and never acts on stale app
state. Cross-round continuity is carried by **you** (this persistent session) plus
`project.md` and the test plan — so if Codex keeps re-learning the same
navigation, enrich `project.md`; do not resume its session.

### 1. Plan

Write a step-by-step manual test plan to `.testloop/test-plan.md`. Every step
must have an **explicit expected result** so a tester can mark it pass/fail. If a
scope was given, cover only that scope, thoroughly. On later rounds, fold in
regression checks for anything you just fixed, and reference the prior
`.testloop/test-results.md`.

Briefly summarize the plan in the conversation before running it.

### 2. Test

You bring the app up; Codex drives it. Do the lifecycle steps yourself with Bash
(you have unsandboxed host access), then hand the running app to Codex.

**a. Build & install** — run `build_cmd` from `repo_dir` (foreground):

```bash
<build_cmd>   # from config.yaml, e.g. rebuild + copy the .app into /Applications
```

**Confirm it succeeded** — exit code 0, and for desktop the `.app` is actually in
place. If build/install fails, **stop and tell the user** — do NOT continue, or
Codex will drive a **stale build** and produce misleading results.

**b. Launch & confirm ready** — start the app, then confirm it is actually up
before handing off. **Do NOT just sleep a fixed time** — a heavy app or a
login/loading screen can take much longer. Derive the launch from `target_desc` /
`project.md` (macOS desktop: `open -a "<AppName>"`; web/mobile: start or serve it
per `project.md`):

```bash
open -a "<AppName>"
pgrep -f "<AppName>" >/dev/null && echo up || echo "NOT running"
```

Check `project.md` for a readiness signal (a window/screen it should reach, a
port that should respond) and give it time to get there. If it never comes up,
stop and tell the user.

**c. Write the Codex prompt** — write the [prompt
template](#prompt-handed-to-codex) to `.testloop/codex-prompt.txt`, substituting
`target_kind`, `target_desc`, and the contents of `.testloop/project.md`, and
using **absolute paths** for the `.testloop/` files (see the note in that
section). The prompt tells Codex the app is already running and to only drive it.

**d. Run Codex in the background** — clear last round's outputs, then drive:

```bash
rm -f .testloop/test-results.md .testloop/decision.json
# <codex_cmd> from config.yaml, e.g. codex exec --dangerously-bypass-approvals-and-sandbox
cat .testloop/codex-prompt.txt | <codex_cmd> 2>&1 | tee .testloop/codex-last.log
```

Launch this with `run_in_background: true` so a multi-minute run is not killed by
the foreground timeout. Codex buffers its stdout when it is not on a TTY, so the
log fills in bursts. Poll it to track progress:

```bash
tail -n 40 .testloop/codex-last.log
```

For a **live** view, tell the user they can follow the log in a separate terminal
with `tail -f .testloop/codex-last.log` — or just watch the app on screen (the
"Codex is using your computer" overlay shows it working even while text is
buffered).

**e. When Codex finishes:**

- **Verify Codex wrote results.** If `.testloop/test-results.md` is missing or
  empty, or the run exited non-zero, stop and tell the user what happened — don't
  fabricate results. Check the tail of `.testloop/codex-last.log` for why.
- **Handle escalations.** If `.testloop/decision.json` appears, Codex escalated a
  question it couldn't decide. Read it, relay the question to the user, get an
  answer, write it to `.testloop/decision-answer.txt`, add the "A human answered
  your previous escalation" paragraph (see the template) to
  `.testloop/codex-prompt.txt`, and re-run Codex from step d (the app is still
  running).
- **Stop the app** once you have the results — macOS desktop: `osascript -e 'quit
  app "<AppName>"'`; web/mobile: stop the server/simulator however it was started
  — unless you are immediately re-running Codex against it.

> Tip: append `--json` to `codex_cmd` if you want finer-grained, per-event
> progress in the log instead of Codex's end-of-run text dump.

### 3. Judge

Read `.testloop/test-results.md` and classify the round out loud as exactly one
of:

- **pass** — every step passed. The loop is done; report success and stop.
- **code-fix** — a real bug in the app code. Go to step 4.
- **retest** — no code change needed, but the test conditions were wrong or flaky;
  adjust the plan and start a new round (do not touch code).
- **human** — you cannot confidently tell whether this is a real bug or expected
  behavior. Stop, explain the ambiguity, and ask the user to decide.

State the failing steps and your reasoning.

### 4. Fix

For **code-fix**: make the minimal code change in the repo (`repo_dir` from
config — the project root) to fix the failing behavior. Explain each change. Then
archive the round and loop back to step 1 to re-verify:

```bash
# snapshot this round's artifacts (skip any that don't exist)
mkdir -p .testloop/iterations/round-N
cp .testloop/test-plan.md .testloop/test-results.md .testloop/iterations/round-N/ 2>/dev/null
```

(Replace `N` with the round number.)

### 5. Next round

Increment `N`. If `N` exceeds `max_rounds`, stop and summarize what still fails
and what you tried. Otherwise start a new round at step 1, re-testing the fix and
watching for regressions.

## Stopping

Stop and report when any of these is true:
- **pass** — all tests green.
- **max_rounds reached** — summarize remaining failures.
- **human decision needed** — a `human` verdict or a Codex escalation you can't
  resolve without the user.

## Prompt handed to Codex

Write this to `.testloop/codex-prompt.txt` each round, replacing the
`<placeholders>` with values from `config.yaml` and the contents of `project.md`.

**Use absolute paths.** Substitute `<abs>` with the project's absolute path (run
`pwd`). Codex may change directories while driving and inspecting the app, so
relative `.testloop/` paths would make it read the plan or write results in the
wrong place — and the loop would then wrongly conclude Codex produced nothing.

```text
You are executing a test plan by driving an app via computer use.
App under test (<target_kind>): <target_desc>

Project profile (background context):
<contents of .testloop/project.md>

The app is ALREADY built, installed, and running on screen. Do NOT build,
install, relaunch, or quit it -- just drive its GUI (bring it to the foreground
if needed) and run the plan against it. If it is still loading or on a splash
screen, wait until it is ready before you start.

Read the plan from <abs>/.testloop/test-plan.md. Execute every step. Write results
to <abs>/.testloop/test-results.md: for each step record PASS or FAIL, and for any
failure include concrete reproduction steps and observed vs expected behavior.

If you cannot decide something on your own (ambiguous trade-off, unexpected
situation, unclear requirement), DO NOT guess. Instead write a JSON object to
<abs>/.testloop/decision.json of the form {"needs_decision": true, "question":
"<your question>", "options": ["<option A>", "<option B>"]} and stop. A human will
answer and you will be re-run with the answer.
```

**On a re-run after an escalation only,** insert this paragraph right before the
final "If you cannot decide" paragraph (drop it on the first run):

```text
A human answered your previous escalation with:
<contents of .testloop/decision-answer.txt>
Incorporate this answer and proceed.
```

## Templates

### `.testloop/config.yaml`

```yaml
# testloop project config
repo_dir: .                      # where Claude fixes bugs (project root)
target_kind: web                 # web | desktop | mobile (informational)
target_desc: |
  Describe the app under test so Codex knows what it is driving.
  e.g. A web app served at http://localhost:3000; main screen is ...

# How to build/install the app under test. Run by you (the main agent) via Bash
# before each round -- NOT by Codex -- so it is built and installed ready to
# launch. Desktop: must yield a real, installed app -- not a dev server.
build_cmd: pnpm build

# How Codex is invoked to DRIVE the running app. Run WITHOUT a sandbox: Codex
# drives the GUI via computer use (screenshots + clicks -- side effects a sandbox
# blocks) and writes results. `--dangerously-bypass-approvals-and-sandbox` also
# skips approval prompts so the background run is never left waiting on one.
# `-c model_reasoning_effort=medium` keeps thinking moderate -- driving a GUI to
# a written plan rarely needs max reasoning; raise to high/xhigh if Codex fumbles
# the steps (or drop the flag to inherit your ~/.codex/config.toml default).
codex_cmd: codex exec --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort=medium

max_rounds: 8                    # hard backstop against infinite loops
```

### `.testloop/project.md`

```markdown
# Project profile

_Shared context testloop gives to Codex each round. Edit freely._

## Overview
TODO: what this project is.

## Structure
TODO: key directories/modules and what they do.

## How to launch
TODO: how the app is built and started for testing.

## How to run tests
TODO: existing test commands / how testing works here.

## Notes
TODO: gotchas, prerequisites, things to watch out for.
```

## Files (all under `.testloop/`)

| File | Written by | Purpose |
|---|---|---|
| `config.yaml` | you (setup) | `build_cmd`, target kind, `codex_cmd`, `max_rounds` |
| `project.md` | you (setup) | project profile (shared context) |
| `test-plan.md` | you | the round's plan, steps with expected results |
| `codex-prompt.txt` | you | the prompt handed to Codex this round |
| `test-results.md` | Codex | per-step PASS/FAIL + repro for failures |
| `codex-last.log` | Codex run | durable stream of the last run; `tail -f` to watch progress |
| `decision.json` | Codex | an escalated question when Codex can't decide |
| `decision-answer.txt` | you | the user's answer to a `decision.json` |
| `iterations/round-N/` | you (step 4) | per-round snapshot |

These are scratch artifacts. On first run, if `.testloop/` is not already
ignored, offer to add `.testloop/` to the project's `.gitignore` so runs don't
clutter the user's working tree.
