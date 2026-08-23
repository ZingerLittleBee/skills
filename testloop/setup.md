# testloop — first-run setup

`.testloop/config.yaml` (build command, Herdr tester settings, `max_rounds`) and
`.testloop/project.md` (the project profile used as shared context) are the
loop's inputs. Fill them in yourself — inspect the project and write the real
values.

For a project configured by an older testloop version, replace `codex_cmd`
instead of keeping both formats. Set `test_agent_kind: codex`, preserve the
interactive flags that followed `codex exec` under `test_agent_args`, translate
`--yolo` to `--dangerously-bypass-approvals-and-sandbox`, drop exec-only flags,
and add `test_timeout_ms`. Verify the result against `codex --help`, then show
the migrated tester settings to the user before running.

1. Scaffold both files from the [templates below](#templates) — write them
   verbatim, then replace the placeholders. Create the dir first:
   `mkdir -p .testloop`.
2. Inspect the project **yourself** — directory layout, `package.json` scripts,
   `tauri.conf.json` / `Cargo.toml` / vite / next config, `CLAUDE.md`,
   `AGENTS.md` — and edit the two files with real values:
   - `config.yaml`: real `build_cmd`, `target_kind` (`web` / `desktop` /
     `mobile`), `target_desc`, `test_agent_kind`, `test_agent_args`,
     `test_timeout_ms`, `max_rounds`.
   - `project.md`: overview, structure, how to launch, how to test, gotchas.
3. **Show the user the filled-in `config.yaml` and confirm** the `build_cmd`,
   `test_agent_kind`, and `test_agent_args` before continuing.
4. Most `.testloop/` files are scratch artifacts, but the loop's final step
   writes a concise per-run report to `.testloop/reports/` that is meant to be
   committed. Offer to add this to the project's `.gitignore`:

   ```gitignore
   .testloop/*
   !.testloop/reports/
   ```

   Ignoring `.testloop/*` (the contents) instead of `.testloop/` (the directory)
   is what makes the `!` re-include work — git never descends into a fully
   ignored directory. If the project already ignores `.testloop/` from an
   earlier setup, update it to this pattern, or reports will silently stay
   untracked.

## Desktop apps — install a real build, don't use a dev server

For `target_kind: desktop`, Codex drives the app through the OS as a normally
**installed application**. So `build_cmd` must produce a real, installed app —
do NOT point it at a dev server (`pnpm tauri dev`, `npm start`, an Electron dev
window, etc.), because computer use can't reliably target a transient dev
process.

The build command depends on the toolchain, so **inspect the project and
decide** — it may be Tauri, Electron, Flutter, native, or a custom bundler
script. Its job is to **build a debug/local bundle and install it into the
platform's app location** (macOS: the `.app` into `/Applications`; derive
`<AppName>` from `target_desc` / `project.md`). Read `package.json` scripts and
the bundler config, prefer the debug/unsigned build (faster, fine for local
testing), and **confirm the resulting `build_cmd` with the user** before
running. For example, a Tauri project's `build_cmd` typically looks like:

```yaml
build_cmd: >-
  pnpm tauri build --debug &&
  rm -rf "/Applications/<AppName>.app" &&
  cp -R "src-tauri/target/debug/bundle/macos/<AppName>.app" /Applications/
```

— but an Electron app, a custom bundler script (e.g. a `universal` / `package`
npm script), signing, or notarization can change both the build command and the
output path. Treat the Tauri snippet as an illustration, not a default.

## Templates

### `.testloop/config.yaml`

```yaml
# testloop project config
repo_dir: /absolute/path/to/project  # project root; must be absolute
target_kind: web                 # web | desktop | mobile (informational)
target_desc: |
  Describe the app under test so Codex knows what it is driving.
  e.g. A web app served at http://localhost:3000; main screen is ...

# How to build/install the app under test. Run by you (the main agent) via Bash
# before each round -- NOT by Codex -- so it is built and installed ready to
# launch. Desktop: must yield a real, installed app -- not a dev server.
build_cmd: pnpm build

# Herdr starts this interactive agent in a sibling pane. The kind must be listed
# by `herdr agent`; native agent arguments follow Herdr's `--` separator.
test_agent_kind: codex
test_agent_args:
  - --dangerously-bypass-approvals-and-sandbox
  - -m
  - gpt-5.6-terra
  - -c
  - model_reasoning_effort=medium

# Wall-clock deadline for one tester prompt. The Herdr watch loop wakes on state
# changes and at least every 60 seconds; reaching this deadline is an operational
# timeout, not a test verdict.
test_timeout_ms: 1800000

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
