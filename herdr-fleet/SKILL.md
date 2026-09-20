---
name: herdr-fleet
description: "Run one round of parallel implementation across multiple CLI coding agents (claude, codex, grok, agy, droid, …) in herdr-managed git worktrees, one package per worktree, merged back into one local branch. Models are picked per role through named slots with fallback candidates. Invoke with /herdr-fleet followed by tasks or a backlog description."
disable-model-invocation: true
---

# herdr-fleet

Complete several work packages in parallel by giving each one a git
worktree and a dedicated CLI coding agent inside herdr. You are the
**orchestrator**: the round's main agent and the only one the user
talks to. Like any coding session you read what you need in order to
decide, run commands, and keep the ledger. What you never do is
implement a package or grade a package diff: implementation belongs to
**implementer** agents in their own worktrees, grading to **reviewer**
agents in their own panes, and bulk exploration to read-only **scout**
agents that return summaries. Every agent you start runs in an
auto-approving mode; approval questions reach the user through you
alone. That split is what makes the round safe: your context stays a
context of decisions rather than of source, and no two writers ever
share a checkout.

## 1. Roles and model slots

Four roles. Each one names the **slot** it runs on, its write scope,
and what it hands back:

| Role | Slot | Writes | Spawns | Hands back |
|---|---|---|---|---|
| Orchestrator | the user's own session | manifest, briefs, check scripts | every fleet agent | the final report |
| Implementer | `smol` / `default` / `slow` by package difficulty | its own worktree only | nothing | commits plus a short summary |
| Reviewer | `review` | nothing (read-only) | nothing | a structured verdict file |
| Scout | `smol` | nothing (read-only) | nothing | a structured report file |

Builds, tests and worktree preparation are commands the orchestrator
runs in dedicated shell panes (steps 4, 8, 9), not agents. Conflict
resolution and merge-suite fixes are the Implementer role working in
the merge tab (step 9); grading those fixes is the Reviewer role.

Models are declared once, by name, in a **model catalog**: each entry
is an agent kind plus the exact arguments that select that model, its
reasoning level and its auto-approving mode. A **slot** is an ordered
list of catalog names, the candidates. Arguments live only in the
catalog; slots, briefs and the manifest refer to models by name:

| Slot | Used for |
|---|---|
| `smol` | scouts; mechanical, well-bounded packages |
| `default` | ordinary packages |
| `slow` | foundational, concurrent, security-sensitive or data-model packages; adjudicating re-grades |
| `review` | every reviewer; must not share a vendor with `default` or `slow` |

The catalog and the slot table are the user's, not the skill's: read
both from `${XDG_CONFIG_HOME:-$HOME/.config}/herdr-fleet/slots.yml`.
Its shape, with example values:

```yaml
models:
  claude-opus-5:      { kind: claude, args: "--dangerously-skip-permissions --model claude-opus-5" }
  claude-haiku-4.5:   { kind: claude, args: "--dangerously-skip-permissions --model claude-haiku-4-5-20251001" }
  gpt-6-astra-medium: { kind: codex,  args: "--dangerously-bypass-approvals-and-sandbox -m gpt-6-astra -c model_reasoning_effort=medium" }
  gpt-6-astra-xhigh:  { kind: codex,  args: "--dangerously-bypass-approvals-and-sandbox -m gpt-6-astra -c model_reasoning_effort=xhigh" }
  gemini-3.8-flash:   { kind: agy,    args: "--dangerously-skip-permissions --model gemini-3.8-flash --effort low" }
  grok-4.6:           { kind: grok,   args: "--permission-mode bypassPermissions --model grok-4.6" }
slots:
  smol:    [gemini-3.8-flash, claude-haiku-4.5]
  default: [gpt-6-astra-medium, claude-opus-5]
  slow:    [gpt-6-astra-xhigh, claude-opus-5]
  review:  [grok-4.6, claude-opus-5]
```

A model's **vendor** is its `kind` unless the entry declares a
`vendor` field (needed when one CLI fronts another vendor's model, as
`omp` does); the cross-vendor rule for `review` compares vendors. If
the file is missing, ask the user once which models they have and
which slot each should serve, and write the file for them before
continuing. Per-kind arguments that
turn on auto-approving mode and select the model, as verified against
the installed CLIs:

| kind | binary | auto mode | model / reasoning |
|---|---|---|---|
| claude | `claude` | `--dangerously-skip-permissions` | `--model <m>`, `--effort <level>` |
| codex | `codex` | `--dangerously-bypass-approvals-and-sandbox` (never a sandbox) | `-m <m> -c model_reasoning_effort=<low\|medium\|high\|xhigh>` |
| cursor | `cursor-agent` | `--yolo --trust` | `--model <m>` |
| grok | `grok` | `--permission-mode bypassPermissions` | `--model <m>`, `--reasoning-effort <e>` |
| agy | `agy` | `--dangerously-skip-permissions` | `--model <m> --effort <low\|medium\|high>` |
| droid | `droid` | `--auto high` | model from droid's own config |
| devin | `devin` | `--permission-mode dangerous` | `--model <m>` |
| omp | `omp` | `--approval-mode=yolo` | `--model <m>` |

Every candidate carries its auto-mode argument: a fleet agent that
stops at an approval prompt stalls its package until the watch loop
notices. The arguments go after `--` on every start:

```bash
herdr agent start <name> --kind <kind> --pane <pane-id> -- <candidate-args>
```

**Slot resolution** happens once per round, in step 2: a candidate
whose binary is missing (`command -v <binary>`) or whose herdr
integration cannot be brought to `current` is dropped for the round;
the first surviving candidate is the slot's active one. There is no
probing beyond that. A candidate that turns out to be dead at runtime
(quota, outage, bad model name) is handled by the **slot fallback**
rule in step 6: the agent is replaced from the next candidate and the
slot's pointer moves on for the rest of the round. The active
candidate per slot is shown in the step 3 plan and recorded in the
manifest (step 4); every fallback is recorded too, so the final report
can say which model actually did each package.

## 2. Preconditions

- Confirm the herdr server is reachable: `herdr status server` must
  report `status: running`. The orchestrator itself need not run
  inside a herdr pane (the CLI reaches the server over its socket, and
  every target in this flow is an explicit id) but every agent it
  drives does. If the check fails, say so and stop.
- Resolve the **orchestrator workspace**, the workspace that hosts the
  round's own tabs (scout tabs in step 3, the merge tab in step 9).
  Inside herdr (`test "${HERDR_ENV:-}" = 1`) it is
  `$HERDR_WORKSPACE_ID`; it belongs to the user and the round never
  closes it. Outside herdr no workspace is implied, so the round
  creates one of its own in step 3 and closes it in step 10.
- The main repo's working tree must be clean (`git status`); surface a
  dirty tree instead of working around it.
- Resolve the four slots (step 1). For each candidate, in order: check
  the binary with `command -v`, then `herdr integration status` for
  its kind, running `herdr integration install <kind>` when it reads
  `not installed` or `outdated`; the watch loop's state detection comes
  from that integration. Drop candidates that fail either check. A
  slot with no surviving candidate stops the round here: report it and
  ask the user. Confirm the `review` slot's active candidate differs in
  vendor from the active `default` and `slow` candidates; if it does
  not, advance `review` to the first candidate that does.
- This is a long, hands-off run. If your own session is not in an
  auto-accepting permission mode, warn that every approval prompt
  stalls the round.

herdr CLI basics that the whole flow relies on: control commands
return JSON; read every workspace/tab/pane id from the response
(`.result.workspace`, `.result.root_pane.pane_id`, …), never guess
them. Agent states: `working` (leave it alone), `blocked` (it needs
input), `idle`/`done` (turn finished), `unknown` (present but
unclassified, not proof of completion). A package is **settled** when
its agent reads `idle` or `done`; an `unknown` agent must be read
before it counts as anything.

**Turn discipline.** The round runs unattended and the user is not
watching in real time, so end a turn only at these points: the plan
and worktree-disposition confirmation (step 3), the post-drop
confirmation (step 7), an agent question that needs the user's
authority or an exhausted slot (step 6), a merge-target suite failure
the round cannot resolve (step 9), and the final report (step 10).
Nothing else ends a turn: not "waiting for the agents", not a long
context, not a phase boundary. Before ending any turn, check the last
paragraph: if it is a plan, a list of next steps, or a promise about
work not yet done ("next I'll merge…", "then cleanup…"), do that work
now with tool calls, retrying after errors and gathering missing
information yourself. Do not stop for permission on work the round
already covers; the user's confirmation at step 3 (or their
instruction to run unattended) is the authority for steps 4 through
10.

**Context discipline.** The orchestrator is the most expensive model
in the fleet and every tool call re-sends its whole context, so keep
source and logs out of it: scouts return summaries, verdicts are
read through `jq` for their blocking findings only (step 7), check
reports are read for their first line only (step 8), and failing
output travels to an implementer as a file path, never as pasted
text. Read a file in full only when a decision genuinely turns on
its contents.

## 3. Package the work

Understand the request the way you would in any session: read the
user's description, the repo's convention files, the file tree, and
`git log`, and open the specific files a slicing decision hinges on.
Do not walk the codebase yourself. Every question that needs broad
reading goes to a **scout**: the host's own read-only subagent
facility if it has one (an Explore-style agent), otherwise a herdr
agent on the `smol` slot, started in a tab of its own in the
orchestrator workspace (pick the round-slug and record the
orchestrator workspace id, both below, before starting it):

```bash
herdr tab create --workspace <orchestrator-workspace-id> --cwd <main-repo-path> --label <round-slug>-scout-<n> --no-focus
herdr agent start <round-slug>-scout-<n> --kind <kind> --pane <root-pane-id> -- <smol-candidate-args>
```

Several scouts may run at once, each on one narrow question; they
read, so they never contend for build caches. A scout's brief is a
file-drop (step 5) and carries: the question; the rule that it edits
nothing, runs no build and no tests, and spawns nothing; and the
output contract, a report at a fixed path with fixed sections and
only the path as the reply. The report a round always needs, once per
requested task: the files it will touch, its overlap with the other
tasks, a difficulty grade with reasons, and the convention files,
glossary and design specs the implementer must read, by path. And
once per repo: the dependency-resolution command, any large ignored
build artifacts a worktree will need, the build command, and the
per-package quick-check command, which feed steps 4 and 8. When a
report leaves a slicing decision open, ask that scout a follow-up in
its pane rather than reading the code yourself; it is shut only after
the plan is confirmed.

Scouts started as herdr agents are pre-ledger resources (the round
directory does not exist yet; a round-created workspace, below, is the
only other one): their reports are written to
`"${TMPDIR:?}/herdr-fleet-<round-slug>-scout-<n>.md"`, each agent is
shut and its tab closed (step 9 shutdown procedure) before step 4
begins, and the report files are moved into the round directory once
that exists in step 4, so they are reclaimed with the round.

Group the requested tasks into packages that can genuinely run in
parallel, and slice aggressively: parallel wall-clock is the point of
the round, so whenever a task decomposes into independent pieces, make
each piece its own package rather than one long serial one. Serialize
only what truly depends on another package's output:

- One package = one branch = one agent. Keep each package small enough
  that a single agent finishes it in one sitting.
- Minimize file overlap between packages. Where two packages must touch
  the same file, note it as a merge risk up front and decide their
  merge order now: a shared *base* commit merges cleanly, but two
  packages editing the same lines will not.
- Write down, per package: scope, acceptance criteria, the design or
  spec references the agent must read, a difficulty grade, and the
  slot that grade maps to (step 5).

Give the round a short kebab-case **round-slug** and each package its
own slug. The package slug names everything the package owns: branch
`feat/<slug>`, worktree label, implementer agent `<slug>`, reviewer
agent `<slug>-review`, check pane, and brief file, so `herdr agent
list` reads as a status board. The round-slug names the scouts
(above), the brief directory (step 5), the merge tab (step 9) and,
when the round needs a fresh merge target, that branch (below). Agent
names are server-global and branches already live in the repo: check
`herdr agent list` and `git branch --list "feat/*"` for collisions
now, the round-slug branch included, and pick a different slug rather
than debug ambiguous targets mid-round. Also refuse a round-slug whose
`"${TMPDIR:?}/herdr-fleet-<round-slug>"` already exists: that leftover
is an interrupted round's ledger; recover it in step 10 rather than
adopting it, and pick a new slug if it remains.

Now fix the round's **base** and **merge target** from the main repo's
current branch:

- Record the main repo's absolute path (`git rev-parse
  --show-toplevel`), the current branch (`git rev-parse --abbrev-ref
  HEAD`), and its head sha (`git rev-parse HEAD`). The sha is the
  round's base, every worktree gets pinned to it (step 4), and the
  path is what worktree creation (step 4) and merge briefs (step 9)
  reference; your shell's cwd hours from now is not a substitute.
- Record the orchestrator workspace id (step 2). Inside herdr, take
  it from `printf '%s\n' "$HERDR_WORKSPACE_ID"`. Outside herdr,
  create the round's workspace now and read
  `.result.workspace.workspace_id` from the JSON:

  ```bash
  herdr workspace create --cwd <main-repo-path> --label <round-slug> --no-focus
  ```

  That recorded orchestrator workspace id is what later binds the
  scout tabs (above) and the merge tab (step 9) to this workspace;
  the globally active workspace is not a substitute. A round-created
  workspace is a pre-ledger resource like the scouts: append its
  `created` event (`kind` `workspace`, `role` `round-workspace`,
  `cleanup_policy` `close-container`) right after the round-dir event
  in step 4, and close it in step 10. Its initial tab and root pane
  stay untouched; the round only adds tabs to it.
- If the current branch is shared and long-lived (the default branch,
  `develop`, `release/*`), or HEAD is detached (`--abbrev-ref` prints
  the literal `HEAD`), the round must not land on it directly: the
  merge target is a new local branch `feat/<round-slug>` created from
  the base sha at merge time (step 9). Otherwise the current branch
  itself is the merge target. Borderline cases are your judgment call.

Inventory the source repo's existing worktrees: detached or prunable
entries, a target path occupied by a different branch, checkouts whose
herdr workspace closed while the directory remains, and prior rounds'
disk cost:

```bash
herdr worktree list --cwd <main-repo-path>
git -C <main-repo-path> worktree list --porcelain
```

List read-only and ask the user to decide reuse / remove / keep for
each; never auto-clean a prior round's resources.

Present the plan as a short table and get one confirmation before
creating anything (skip only if the user already said to run
unattended): packages, branch names, merge order, merge target, slot
per package, the active candidate per slot from step 2, and those
worktree decisions. The user may override slots here ("this round,
codex only"); apply the override by filtering candidates, not by
editing the slot file.

## 4. One worktree per package

Persist an append-only JSONL manifest at
`<round-dir>/manifest.jsonl`. The round directory is the ledger's
home, so it cannot be preceded by its own `intent`. Resolve
`"${TMPDIR:?}/herdr-fleet-<round-slug>"` to an absolute path; the
`:?` fails closed if `TMPDIR` is unset. If that path already exists,
recover it in step 10; do not `mkdir -p` and do not adopt it. Only
once the path does not exist, `mkdir` (not `mkdir -p`) so a race
still fails, and immediately append `created` for the round
directory (`kind` `dir`, `role` `round-dir`, `cleanup_policy`
`delete-on-success`) with that resolved absolute path in `selector`
and `observed` before doing anything else; step 5 reuses this
recorded path, never a second `$TMPDIR` resolve. Then, if the round
created its own workspace (step 3), append its `created` event with
the recorded workspace id; move any scout reports from `$TMPDIR`
(step 3) into the round directory; and append one `slot` event per
slot with the active candidate (`resource_key` `slot/<name>`, `kind`
`slot`, `observed` carrying the model name, `kind` and `args`). Mint a `round_id`
unique to this invocation; ownership is proved by `round_id`, not by
round-slug or label. `seq` increases monotonically so an auditor can
detect a truncated or misordered append.

A mutable row cannot be write-ahead, so this is an event log: write an
`intent` event and flush it before each create command; append a
`created` event immediately after a successful response, before doing
anything else; append a `state` event on disposition; append a `slot`
event on every slot resolution and fallback. Never rewrite an earlier
line. Every later resource follows that write-ahead, including every
agent, pane, tab, branch, container root pane, and worktree parent
directory; only the round directory (so the ledger can exist) and the
pre-ledger resources of step 3 (a round-created workspace, scout
tabs) precede their own events, and an unrecorded resource cannot be
reclaimed.

Record envelope:

```json
{
  "schema_version": 2,
  "round_id": "<unique per invocation>",
  "round_slug": "<slug>",
  "seq": 1,
  "event": "intent | created | state | slot",
  "resource_key": "package/<slug>/worktree",
  "kind": "worktree | workspace | tab | pane | agent | branch | dir | slot",
  "role": "package-container | package-implementer | package-reviewer | check-pane | review-pane | merge-container | merge-implementer | merge-reviewer | merge-check-pane | package-branch | round-dir | round-workspace | merge-target | worktree-parent-directory | round-archive | container-root-pane | slot",
  "parent_key": "<logical parent resource_key or null>",
  "cleanup_policy": "remove-when-merged | close-aux | close-container | retain-if-unmerged | delete-on-success | report-only",
  "selector": {},
  "observed": {},
  "status": "planned | live | removed | retained | failed",
  "detail": "<reason or sanitized error, or null>"
}
```

`resource_key` ties the write-ahead `intent`, the `created` event and
later `state` events together. `parent_key` is logical, so it exists
before the parent's herdr id is known. `cleanup_policy` is
load-bearing: a later auditor cannot otherwise tell whether a live
resource should be closed, removed only after reachability checks, or
deliberately retained. `selector` is structured expected identity,
used to find the resource again if a create response is lost.
`observed` is empty on `intent` and carries the real ids on
`created`. Agent `created` events also carry the slot name and the
candidate's model name, `kind` and `args` in `observed`, so the report
can name the model behind every package.

Before each `herdr worktree create`, append `intent` for the worktree
(`package/<slug>/worktree`, `kind` `worktree`, `role`
`package-container`, `cleanup_policy` `remove-when-merged`), its
branch (`package/<slug>/branch`, `kind` `branch`, `role`
`package-branch`), its container root pane (`role`
`container-root-pane`, `cleanup_policy` `close-container`), and the
worktree parent directory (`kind` `dir`, `role`
`worktree-parent-directory`, `cleanup_policy` `delete-on-success`).

```bash
herdr worktree create --cwd <main-repo-path> --branch feat/<slug> --base <sha> --label <slug> --no-focus
```

Pin every package to the same `--base` commit (the round's base sha
from step 3): it keeps packages from drifting apart if the branch
moves mid-round, and every later verification diffs against it.

Append `created` for all four from the JSON (workspace id, root pane
id, and path on the worktree and container-root-pane; branch ref;
parent path). Reviewers (step 7) and quick checks (step 8) need the
worktree path.

**Prepare the worktree yourself, in a check pane.** The worktree still
has to be made buildable before an implementer starts in it. Right
after the worktree's `created` events, split a **check pane** off the
root pane, write-ahead it (`role` `check-pane`, `kind` `pane`,
`cleanup_policy` `close-aux`), and read the new pane id from the JSON:

```bash
herdr pane split <root-pane-id> --cwd <worktree-path> --no-focus
```

Commands that run in a check pane are **check scripts**: bash files in
the round directory, one per run, so quoting never depends on the
pane's shell and the exact command survives for the report. A check
script sets `-o pipefail`, runs its commands with all output redirected
to a log in the round directory, writes a report whose first line is
`PASS <sha>` or `FAIL <sha>` followed by the verbatim log, and ends by
printing one **marker** line unique to this run, which is what you
wait on. Skeleton, with `<sha>` the base sha for preparation and the
candidate sha in step 8, and `<attempt>` a counter you increment per
run so a stale marker from a previous run can never match:

```bash
#!/usr/bin/env bash
set -o pipefail
log="<recorded-round-dir>/<slug>-<phase>-<sha>-<attempt>.log"
report="<recorded-round-dir>/<slug>-<phase>-<sha>.md"
{ cd "<worktree-path>" && <command-1> && <command-2>; } >"$log" 2>&1
rc=$?
{ if [ "$rc" -eq 0 ]; then echo "PASS <sha>"; else echo "FAIL <sha>"; fi; echo; cat "$log"; } >"$report"
printf 'FLEET <slug> <phase> <sha> <attempt> exit=%s\n' "$rc"
```

Run it and block on the marker, then read the report's first line
(the exit status is in the marker; the log is for the implementer, not
for you):

```bash
herdr pane run <check-pane-id> "bash <recorded-round-dir>/<slug>-<phase>-<sha>-<attempt>.sh"
herdr pane wait-output <check-pane-id> --match "FLEET <slug> <phase> <sha> <attempt> exit=" --timeout 900000
head -n 1 <recorded-round-dir>/<slug>-<phase>-<sha>.md
```

The preparation script (`<phase>` `prep`) carries:

- **Binary artifacts don't follow.** Git worktrees share history, not
  ignored build artifacts. For each large local artifact the build
  depends on (a prebuilt xcframework, a vendored binary; the scout
  report lists them), copy the real directory from the main repo into
  the worktree; symlinks often defeat build systems that resolve
  artifact identity through the path.
- The project's dependency-resolution command from the scout report
  (e.g. `swift package resolve`, `pnpm install`), run once in the
  worktree. A transient network failure is a retry with the next
  attempt number, not evidence that the worktree is broken.
- No build and no test run: preparation only.

Resolution contends for the same shared caches as builds, so prepare
one worktree at a time and wait for its marker before starting the
next. The check pane stays open, at an idle shell, until step 8 needs
it.

## 5. Start and brief each implementer

Map each package's difficulty grade to a slot. Foundational or
architecturally risky packages (data models, concurrency, security,
anything other packages build on) go to `slow`: a weak foundation
costs every reviewer and every later round. Mechanical, well-bounded
packages (apply an established pattern, styling sweeps, copy changes,
renames) go to `smol`. Everything else is `default`. When unsure,
assign up. Write-ahead the implementer (`kind` `agent`, `role`
`package-implementer`, slot name in `selector`) and append `created`,
with the candidate actually used, after a successful start:

```bash
herdr agent start <slug> --kind <kind> --pane <root-pane-id> -- <candidate-args>
```

A real brief is too long to push through a terminal. Write it as a
Markdown file, one per package, in the round directory recorded on
the round-dir `created` event in step 4 (that absolute path, not a
fresh `$TMPDIR` resolve; do not `mkdir` it again). One brief per
package at `<recorded-round-dir>/<slug>.md`; prompt with a one-liner:

```bash
herdr agent prompt <slug> "Read <recorded-round-dir>/<slug>.md and complete the package it describes."
```

Long text sent through `agent prompt` risks wrapping and paste-mode
mangling, and a file survives for re-briefing after a crash, a
swallowed prompt, or a slot fallback. This is the **file-drop** rule,
and it covers everything long you send an agent all round: briefs,
review feedback, failing build output. Write a file in the round
directory, send the path. Write the file with the same discipline as
a handoff document: self-contained, referencing specs and code by
path instead of inlining them, and with secrets redacted, since the
agent's pane is visible to anyone at the screen.

The brief must carry:

- The package scope and acceptance criteria, plus pointers to the
  repo's convention files (CLAUDE.md / AGENTS.md), glossary, and any
  design specs; tell the agent to read them first.
- **Write tests, but do not run the heavy build or test suite.** The
  orchestrator runs the package's quick checks afterwards, serially,
  one build at a time. Explain why in the brief: concurrent builds
  across worktrees fight over shared caches and locks and make the
  machine unusable, so a parallel round only works if exactly one
  build runs at a time.
- For a `smol` package only: the work is strictly mechanical. Where a
  step needs a judgment call the brief did not make, stop, commit what
  is done, and report the question instead of guessing.
- Commit discipline: Conventional Commits, imperative lowercase subject
  ≤72 chars, no Co-Authored-By trailers or generation watermarks.
  Commit on the package branch. Do not push.
- End-of-turn contract: a summary of changes with file references, and
  a list of anything skipped or uncertain.

## 6. Watch the round: this is your job now

Between briefing and the final merge, the orchestrator's whole job is
the watch loop. Do not end the turn to "wait for the agents", and do
not drift into side work; an unwatched fleet stalls: a `blocked` agent
burns wall-clock until someone answers it, and a crashed agent
silently drops its package.

Loop until every package has **concluded**: passed review (step 7)
and its quick checks (step 8), or been dropped. Settled is not
concluded: review findings and failing output send an agent back to
`working`, and its package re-enters the loop. Sleep-polling burns a
tool call a minute to hear "no change"; block on the fleet instead.
`herdr agent wait` returns the moment an agent reaches `idle`,
`done`, or `blocked`, and costs nothing while it waits:

```bash
bash -c '
for a in <unsettled agent names>; do herdr agent wait "$a" --timeout 540000 & done
wait -n; kill $(jobs -p) 2>/dev/null'
herdr agent list
```

Wake on the first event, sweep with `herdr agent list`, act, then
block again on whatever is still unsettled. Details that keep the
block safe, verified against a live fleet:

- Run the block under a bash ≥ 4.3: `wait -n` is a bash-ism that
  macOS's stock bash 3.2 predates, and zsh or fish error out and leak
  the background waits. Check once with
  `bash -c 'echo ${BASH_VERSINFO[0]}'`; without a modern bash, wait on
  one agent at a time and lean on the timeout sweep.
- Wait only on agents that are unsettled *and still listed*: a wait on
  an agent already `idle` returns in milliseconds, and a wait on a
  name that no longer exists fails just as fast with
  `agent_not_found`; either turns the block into a busy-loop. The
  first `agent_not_found` usefully wakes the loop to report a crash,
  but handle the vanished agent (see the traps below) before blocking
  again.
- Keep `--timeout` under this call's own command limit (raise the
  call's limit rather than shrink the wait) and treat expiry as a
  periodic sweep that catches whatever the waits miss: an agent
  vanishing mid-wait, or one stuck in `unknown`, which `herdr agent
  wait` never fires on.
- A quick check (step 8) or merge suite (step 9) running in a check
  pane is not an agent; `pane wait-output` on its marker is the block
  for it. Run that wait in the same background group when a check is
  in flight, so the loop wakes on whichever finishes first.

Keep a per-package status board (agent state, last state change,
slot and candidate in use, `candidate_sha`, `accepted_sha`,
correction cycles used, quick-check state, next action) as a file at
`<recorded-round-dir>/status.md` (the round directory recorded in
step 4), rewritten on every wake, so it survives context compaction.
After a compaction, recover the loop from that file, the manifest,
and a fresh `herdr agent list` sweep, and continue the round rather
than ending the turn; a long session is not a reason to stop. When an
agent changes state, read its recent output before deciding anything:

```bash
herdr agent read <name> --source recent-unwrapped --lines 120
```

Priorities inside the loop: answer `blocked` agents first (each is
stalled wall-clock), then act on settled ones (a settled implementer
gets its candidate recorded, its quick check queued, and a reviewer
dispatched; a settled reviewer gets its verdict read, step 7; a
finished check gets its report's first line read, step 8), then check
long-`working` ones: an agent whose output hasn't changed across
several sweeps may be stuck on an unrecognized prompt or spinning;
read the pane and decide. Surface progress to the user at transitions
that matter (package settled, review sent, quick checks passed, merge
landed), not on every wake.

Known traps and how to handle them:

- **Slot fallback.** An agent that reaches `blocked`, `idle` or `done`
  moments after a start or a prompt, with no work done, and whose
  screen (`herdr agent read <name> --source visible`) names a quota,
  usage or rate limit, an overloaded or unavailable model, an unknown
  model name, an expired login, or an HTTP 401/429/5xx, has lost its
  model, not its task. Shut it (step 9 shutdown procedure), mark that
  candidate failed for the rest of the round, and take the slot's next
  surviving candidate (for `review`, skipping any candidate that
  shares a vendor with that package's implementer). Append a `slot`
  event naming the old and new candidate, start the replacement in the
  same pane with the new arguments, write-ahead and `created` as
  usual, and re-brief it with the original brief path plus one
  instruction: read `git log <base-sha>..HEAD` and `git status` in
  the worktree first and continue from the committed state. Every
  later start on that slot uses the new candidate directly; the
  failed one is never retried this round. A slot whose candidates are
  exhausted ends the turn with the question, after doing everything on
  this wake that does not depend on it.
- **Swallowed first prompt.** Some agents (droid, notably) eat a prompt
  sent during their startup/welcome screen. If an agent is `idle`
  shortly after start with no meaningful output and no error on
  screen, re-send the pointer prompt; the brief file is still on disk,
  which is one reason it is a file.
- **`blocked`** means the agent is showing an approval or question UI.
  Read the screen before acting. For a menu, use `herdr agent
  send-keys <name> <key>`. For an in-scope free-text answer, use
  `herdr pane send-text <pane-id> <text>` followed by `herdr pane
  send-keys <pane-id> enter`; `agent prompt` rejects a blocked agent
  with `agent_blocked`. An approval prompt on a fleet agent means its
  auto-mode argument is missing or wrong: answer it, then fix that
  model's `args` in the catalog for the rest of the round. A question that needs new
  authority or a user decision goes to the user instead of being
  answered on their behalf. When that happens, first do everything on
  this wake that does not depend on the answer (answer the other
  blocked agents, record settled candidates, queue checks, dispatch
  reviewers), then end the turn with the question and the current
  status board rather than blocking on `herdr agent wait` again. The
  fleet keeps working in herdr while the user answers; on the reply,
  resume with a `herdr agent list` sweep. Do not answer on the user's
  behalf, and do not hold the question for hours behind another wait.
- **Alternate-screen output is unrecoverable.** Agents that render on
  the terminal's alternate screen never feed scrolled-off rows into
  herdr's scrollback, so raising `--lines` cannot recover a long
  finished reply. When a read comes back truncated, ask the agent to
  write its complete report to a Markdown file in the round directory
  and reply with only the path, then read the file directly.
- **A vanished agent is not a finished agent.** If a name disappears
  from `herdr agent list` and the pane is back at a shell, the agent
  exited or crashed. Check `git log` in the worktree for what actually
  landed, then `herdr agent start` a fresh agent in the same pane, on
  the same slot, and re-brief it with what is already committed.
- Never send a new prompt to a `working` agent: it lands mid-turn and
  corrupts the run. Wait for `idle`/`done`/`blocked`.

## 7. Review each package with a dedicated reviewer agent

When an implementer settles, first check the plumbing yourself; this
is cheap metadata, not source. `git log <base-sha>..HEAD` in the
worktree is the complete set of commits the package produced, taken
from git, never from the agent's summary. Require `git status
--porcelain` to be empty, then record `candidate_sha=$(git rev-parse
HEAD)`. Uncommitted leftovers mean the brief was not followed and
cannot enter either gate. An empty range means the package produced
nothing: re-brief or drop it; an empty branch has nothing to merge and
never reaches step 9.

A candidate is **qualified** by two gates, both bound to that exact
`candidate_sha`: the review gate (this step) and the quick-check gate
(step 8). Run them concurrently (reviews run no builds and grade the
diff from git objects, so neither disturbs the other) and queue the
quick check the moment the sha is recorded. (If the project's build
mutates tracked files, let the quick check finish before dispatching
the reviewer.) While either gate is still running, hold your feedback:
collect both gates' results and send one combined fix brief, so a
build failure and review findings cost one fix cycle, not two. Accept
only when both gates pass the same clean sha, and record it then as
`accepted_sha`. Any retained code change, whatever its cause, is a new
candidate and re-enters both gates.

Hand the diff to a **reviewer agent**, a fleet agent of its own on the
`review` slot, in its own pane, and do not grade it yourself. Package
diffs pulled into the orchestrator are exactly the source this
architecture keeps out: by the fourth package your judgment is
swimming in the first three's implementation noise, and having briefed
the round you also want it to succeed; a reviewer that wrote none of
it, on a different vendor's model, grades without that bias. Split a
review pane off the package's root pane, write-ahead the pane and the
reviewer agent (`role` `review-pane` / `package-reviewer`, `kind`
`pane` / `agent`, `cleanup_policy` `close-aux`), read the new pane id
from the JSON, and start it:

```bash
herdr pane split <root-pane-id> --cwd <worktree-path> --no-focus
herdr agent start <slug>-review --kind <kind> --pane <new-pane-id> -- <review-candidate-args>
```

The reviewer shares the implementer's worktree read-only; the intro's
rule bans two *writers* per checkout, and a reviewer is not one. Its
brief is a file-drop like any other and carries:

- The package brief's path, the worktree path, the base sha, and the
  recorded `candidate_sha`; the instruction to grade
  `git diff <base-sha> <candidate_sha>` against the brief's criteria,
  with evidence, flagging anything outside the brief's scope, and to
  name that exact candidate sha in the verdict.
- **What counts as a finding.** Each one must have a provable impact
  on correctness, security, data integrity, or an acceptance
  criterion; be actionable at a named file and line range; be
  something the author did not intend; and be introduced by this
  candidate, not pre-existing. Style, naming, and "consider" remarks
  are not findings. Rigor is proportionate to the risk the brief
  graded: a mechanical `smol` package with explicit acceptance
  criteria gets a short verdict.
- **The verdict format**, a JSON file at
  `<recorded-round-dir>/<slug>-verdict-<candidate_sha>.json`:

  ```json
  {
    "candidate_sha": "<sha>",
    "overall_correctness": "correct | incorrect",
    "explanation": "<one paragraph>",
    "confidence": 0.0,
    "findings": [
      {
        "title": "<short>",
        "body": "<what is wrong, why it matters, how to verify>",
        "priority": "P0 | P1 | P2 | P3",
        "confidence": 0.0,
        "file_path": "<repo-relative>",
        "line_start": 0,
        "line_end": 0
      }
    ],
    "assumption_check": {
      "assumption": "<the unvalidated shared assumption, or null>",
      "relied_on_by": ["<impl and test locations>"],
      "consequence_if_false": "<...>",
      "external_evidence": "<sources inspected or missing, and applicability>",
      "falsification_check": "<setup, independent source of truth, disproving observation>",
      "status": "designed | executed | not-applicable"
    }
  }
  ```

  `P0` and `P1` are **blocking** (an acceptance criterion fails,
  correctness or security breaks, or the merge is endangered); `P2`
  and `P3` are non-blocking. `overall_correctness` is `incorrect` if
  and only if at least one blocking finding exists; non-blocking
  findings alone never fail the gate. The reply is only the file
  path, since pane scrollback truncates long replies (step 6).
- The review is read-only: a reviewer that "fixes" what it grades
  smuggles unreviewed edits into the merge. It runs no build and no
  tests; grading is reading, and a reviewer that runs the suite
  fights the serial quick checks (step 8) for caches and locks.

**Correlated failures.** Independent reviewers can share the same
wrong assumption; more agreeing reviews do not necessarily increase
reliability in proportion to their number. Every review brief must
require this, and the `assumption_check` object carries the answer
even when there are no findings:

> Identify one critical assumption shared by the implementation and
> its tests that has not yet been validated by external evidence, and
> design a check that could falsify it.

Evidence must be independent of the implementation and its test
expectations, such as a version-matched provider contract or an
observed real-system response; matching mocks, copied fixtures, and
reviewer agreement do not validate the assumption. Designing a check
does not validate the assumption either: `status` says whether it was
only designed or actually executed, with results cited when
available. If no such assumption is found, the object documents the
candidates examined and the external evidence that validates them, or
why none applies; the reviewer must not invent one to fill the field.
Return an incomplete verdict to the reviewer for completion. Missing
evidence alone is not a proven defect; any resulting finding is
classified by the priority rules above. Checks requiring execution go
through a check pane within the round's serial queue; the design
itself grants no execution authority. Re-grades revisit this analysis
for the new candidate and may carry it forward only with an explicit
explanation of why it remains applicable.

Reviewers are fleet agents: the same watch loop, wait block, states,
and traps apply, and a settled reviewer means a verdict file to read.
Reviews run no builds, so any number of reviewers can work while
implementers are still working; the one-heavy-build rule is untouched.
Read a verdict for its decision, not its prose:

```bash
jq '{candidate_sha, overall_correctness, blocking: [.findings[] | select(.priority == "P0" or .priority == "P1")]}' <verdict-path>
```

Reject a verdict whose `candidate_sha` is not the recorded one, or
whose `overall_correctness` contradicts its findings, and send it back
for correction.

You adjudicate. With both gates' results in hand, decide accept, send
back, or drop; that call needs round-level context (merge order,
budgets, how the packages interact) that only you hold. Send the
blocking findings back to the implementing agent as a numbered review
prompt, bundling in any non-blocking ones worth fixing, and wait for
the fix; long feedback is a file-drop (step 5), and the verdict file's
path is enough. A blocking finding is cleared by a fix or by a
reviewer verdict; reclassifying it yourself is how a round quietly
ships a rejected package. When a re-grade surfaces a likely-blocking
issue that sat unchanged in the prior candidate, hand that one finding
to a second reviewer agent started from the `slow` slot for a focused
adjudication (if `slow` shares a vendor with the package's
implementer, use the `review` slot's next candidate instead).

Every fix invalidates the prior candidate sha: repeat the clean-tree
plumbing, record the new one, and run both gates again, the quick
check in full, the review as a **re-grade**. Give the reviewer the
prior verdict's path plus the previous and new candidate shas; it
confirms each blocking finding is resolved, reviews
`git diff <prev-candidate> <new-candidate>` for regressions and scope
creep (reading surrounding code where the delta's semantic effects
demand it) and issues a verdict naming the new sha for the complete
candidate. Fall back to a full `base..candidate` grade when history
was rewritten, the fix broadened scope, or the prior verdict cannot be
established.

Budget 2 **correction cycles** per package, counted monotonically: the
initial review is free, and each rejecting verdict (one with a
blocking finding) that opens a send-back increments the counter.
Quick-check repairs and non-blocking cleanups re-enter the gates but
cost no cycle. A third rejecting verdict drops the package or goes to
the user to extend the budget; never accept a rejected or stale
commit.

After any drop, present the reduced package set and what it no longer
delivers, then get confirmation before merging the remaining packages
(unless the user already authorized unattended continuation after
drops). Closing agent sessions is a package completion criterion. A
dropped package's worktree and branch stay in place for the user to
inspect (its work exists nowhere else) but its implementer and
reviewer sessions close at the drop. An accepted package's sessions
close immediately once both gates have passed and `accepted_sha` is
recorded. Shut each agent and close the review pane and the check pane
with the shutdown procedure in step 9; the package is not concluded
until both names are gone from `herdr agent list` and both auxiliary
panes are closed. Merge-target work uses fresh agents instead of
keeping package sessions alive.

## 8. Quick-check serially, yourself

The quick-check gate waits for no verdict: queue it the moment a
candidate sha is recorded. The check runs in the package's check pane
(step 4) as a check script you write, never in your own window and
never by an agent. **Exactly one check script may be running at any
moment across the whole round**, package quick checks and the merge
suite (step 9) alike: start the next one only after the previous
marker has appeared. That is the one-heavy-build rule, the whole
reason implementers don't build (step 5), and the queue is yours to
keep.

The binding stays with you; it is cheap git metadata, not source.
Before running and again after the marker appears, require
`git status --porcelain` to be empty and both `git rev-parse HEAD` and
`git rev-parse feat/<slug>` to equal the recorded `candidate_sha` in
the package worktree; this binds the tested tree to the same commit
the reviewer grades.

The quick-check script (`<phase>` `check`, `<sha>` the candidate sha)
runs the package's own quick checks only, with the commands from the
scout report (step 3): it compiles, its own tests pass. Never the
repo's full suite, which runs once on the merge target (step 9), where
cross-package failures actually show up. A transient infrastructure
failure (network, a cache lock) is a rerun with the next attempt
number on the same candidate, not a new candidate. The script changes
no code and makes no commits; if the build mutates tracked files, the
post-run clean-tree check catches it and the package goes back to the
implementer with that fact.

Read the report's first line only. `PASS <candidate_sha>` passes the
gate. `FAIL <candidate_sha>` goes into the combined fix brief of step 7
as the report file's path, never as pasted output, and any retained
fix, mechanical or otherwise, is a new candidate for both gates. A
report naming any other sha is discarded and the check rerun. No
changed tree reaches the merge without a matching verdict and a green
check report on its exact sha.

## 9. Merge the round locally

The round ends on a local branch; nothing gets pushed. Publishing
(push, PR, merging into the default branch) stays with the user. Once
every non-dropped package has passed review and its quick checks,
merge only those packages. If none remain, skip to step 10.

Create one merge tab for all merge-phase work, bound to the
orchestrator workspace id recorded in step 3; `--workspace` is
required, because without it `herdr tab create` follows the globally
active workspace and a focus change would place the tab elsewhere.
Write-ahead the tab (`kind` `tab`, `role` `merge-container`) and its
root pane (`kind` `pane`, `role` `container-root-pane`):

```bash
herdr tab create --workspace <orchestrator-workspace-id> --cwd <main-repo-path> --label <round-slug>-merge --no-focus
```

Record the merge tab id and its root pane id. Then split a **merge
check pane** off that root pane with cwd `<main-repo-path>` and
write-ahead it (`role` `merge-check-pane`, `kind` `pane`,
`cleanup_policy` `close-aux`); every suite run of the merge phase is a
check script in that pane. Every merge implementer and merge reviewer
splits inside this tab too; never use `--current` here, and never
close this tab's root pane, since `herdr tab close` reclaims it.

The two roles used here are the same Implementer and Reviewer roles as
in steps 5 and 7, started fresh in merge-tab panes with the main
checkout as cwd. A merge implementer runs on the slot of the package
whose merge it resolves (`default` at least, never `smol`); a merge
reviewer runs on `review`. Every merge-review brief and verdict
carries the same format and the correlated-failure requirement from
step 7, applied to the combined behavior under review.

1. Re-check the main repo: the tree still clean (`git status`) and
   HEAD still on the branch recorded in step 3 (`git rev-parse
   --abbrev-ref HEAD`); hours may have passed, and uncommitted edits
   or a mid-round branch switch would ride into the merges; surface a
   mismatch and go to step 10 instead of working around it. If the
   recorded branch itself is the merge target, require
   `git merge-base --is-ancestor <base-sha> HEAD`; a failure means
   the branch was reset or rewritten, so go to step 10 instead of
   merging packages based on stale history. A branch that moved
   forward while retaining the base may still merge; report it. Then
   check out the merge target: if step 3 chose a fresh target,
   write-ahead the branch (`kind` `branch`, `role` `merge-target`,
   `cleanup_policy` `report-only`) and create it now with
   `git switch -c feat/<round-slug> <base-sha>`; an "already exists"
   refusal means the step-3 collision check was dodged, so go to
   step 10 and surface it. Otherwise stay on the recorded branch.
2. Merge the accepted package branches in the agreed order, one at a
   time. Immediately before each merge, require the package worktree
   to be clean and `git rev-parse feat/<slug>` to equal its
   `accepted_sha`, record `pre_merge_sha=$(git rev-parse HEAD)`, then
   run `git merge --no-ff feat/<slug>`. A clean merge is bookkeeping
   and yours to run; it gets no review. A conflicted merge is
   implementation in the main checkout, not the package worktree.
   Split a pane off the merge tab's root pane; write-ahead the pane
   and the agent (`role` `merge-implementer`, `kind` `pane` / `agent`,
   `cleanup_policy` `close-aux`):

   ```bash
   herdr pane split <merge-root-pane-id> --cwd <main-repo-path> --no-focus
   herdr agent start <slug>-merge --kind <kind> --pane <new-pane-id> -- <candidate-args>
   ```

   Brief it by file-drop to resolve and commit the merge, with the
   package brief's path for intent. Do not reuse the worktree-rooted
   implementer: a path written in a brief does not change a live
   agent's cwd, and the conflict index (`MERGE_HEAD`) exists only in
   the main checkout. Exactly one agent may write the main checkout at
   a time. Once it settles, require a clean committed merge, record
   `candidate_sha=$(git rev-parse HEAD)`, and dispatch `<slug>-merge-review`
   in another pane split the same way off the merge tab's root
   (write-ahead `role` `merge-reviewer`, on the `review` slot) to
   grade `git diff <pre_merge_sha> <candidate_sha>` read-only,
   concentrating on the conflict resolution and combined behavior.
   Accept only a verdict naming that candidate sha with no blocking
   finding. Start the next merge only after this review passes and
   the pair is shut (shutdown procedure below).
3. Run the repo's full build and test suite on the merge target as a
   check script in the merge check pane (`<slug>` the round-slug,
   `<phase>` `suite`, `<sha>` the merge target's current sha): the
   round's heavy build, and the first time the packages meet, so
   cross-package failures land here. Its commands are the full build
   and test commands from the scout report (step 3); it changes no
   code and makes no commits. While it runs, nothing else touches the
   main checkout: no merge implementer is live and you run no git
   there. Read the report's first line. On `FAIL`, record
   `pre_fix_sha=$(git rev-parse HEAD)` and send the report path by
   file-drop to one merge implementer rooted in the main checkout
   (split and write-ahead as in item 2 if needed). Once it settles,
   require a clean tree and a new commit, record
   `candidate_sha=$(git rev-parse HEAD)`, then dispatch a merge
   reviewer (as in item 2) to grade the exact
   `git diff <pre_fix_sha> <candidate_sha>` read-only. Accept only a
   verdict naming that candidate sha with no blocking finding and,
   after the pair is shut (shutdown procedure below), run the suite
   script again on the new sha. Handle one implementer/reviewer pair
   at a time. If a merge implementer is blocked on a user decision, or
   the failure cannot be resolved this round, keep the failing report,
   leave the merge-target red-suite fix state untouched, and go to
   step 10.

Throughout, the main checkout changes hands whole: exactly one agent
or one check script works in it at a time, and while one does, run no
git there yourself; the no-shared-checkout rule from the intro,
applied to you.

**Then shut each finished agent down promptly**, once it is no longer
needed, including each merge pair before the next merge or suite
rerun; do not defer closes to the end of the step. An agent left
running after its package is done keeps a live session holding your
repo context and credentials, keeps occupying a subscription seat,
and will act on any stray input that reaches its pane. Submit the
agent's literal exit command with Enter through its pane, for example
`herdr pane run <pane-id> /quit` for Grok or `herdr pane run
<pane-id> /exit` for agents that use `/exit`; use `herdr agent
send-keys <name> ctrl+c` only as an interrupt fallback after reading
the screen. Confirm the name is gone from `herdr agent list`. Agent
exit is not the end state for an auxiliary pane (check pane, review
pane, merge implementer pane, merge reviewer pane, merge check pane):
once required output is persisted, verify an idle shell with
`herdr pane process-info --pane <pane-id>`, confirm the recorded
container root pane id still exists in the same workspace/tab (check
that id, not a pane count), then `herdr pane close <pane-id>`. Never
close a package workspace root pane or the merge tab's root pane:
`herdr worktree remove --workspace <id>` needs the package workspace
alive, and `herdr tab close` reclaims the merge tab's root. When merge
work is finished, close the merge tab:

```bash
herdr tab close <merge-tab-id>
```

That close is the safety net for any auxiliary pane the prompt closes
missed. Everything the round produced now lives on the merge target;
anything needed after cleanup is a fresh agent's job there.

## 10. Clean up and report

Run this step when merge work finishes, when this round stops after
the round directory exists, and when a later invocation finds a
leftover round directory (steps 3 and 4), and consume that manifest.
A leftover from another invocation needs the user's decision before
anything is destroyed; this round's own abort does not. Shut
still-live agents and auxiliary panes with the step 9 procedure
first, then close a still-live merge tab with
`herdr tab close <merge-tab-id>`. Do not wait for a green suite to
reclaim a package that is already merged: its commits are on the
merge target, and step 9.3 fixes in the main checkout, so that
worktree is not recovery context. Save failing suite output first;
never touch the merge target or its red-suite fix state.

Automatic cleanup candidates are only resources with a manifest
`created` event and no terminal `removed` disposition, intersected
with currently live resources matched by exact recorded id, then
re-verified per kind (identity, parent, occupant, process state, git
path/ref/sha, cleanup policy). Never reclaim `live - manifest`.
`manifest - live` is already-absent: reconcile and report, do not
recreate or delete. An intent-only selector match after a lost
create response is an audit candidate, not automatic destructive
authority.

1. Per package, remove the worktree only when all of these hold:
   `git status --porcelain` is empty, the branch tip equals the
   recorded `accepted_sha`,
   `git merge-base --is-ancestor <accepted_sha> <merge-target>`
   passes, the implementer and reviewer are gone, and every auxiliary
   pane is already closed. Leave the container root pane in place.
   Enumerate the workspace's remaining panes (the recorded root pane
   included) and confirm via `herdr pane process-info --pane
   <pane-id>` that each holds only an idle shell; herdr shuts down the
   workspace's terminal runtimes before a forced removal, so a
   vanished agent does not make `--force` safe. Fail closed on any
   non-shell occupant, user takeover, or unidentifiable state; retain
   and report. Only then `herdr worktree remove --workspace <id>
   --force`. A dirty or unmerged worktree stays in place for
   inspection. A dropped package's worktree (its commits exist nowhere
   else) never gets force-removed; surface it instead. After a
   successful remove, `rmdir` the exact expected empty parent
   directory (non-recursive) and retain on failure. Do not `git
   worktree prune`; at most `git worktree prune --dry-run --verbose`
   and report the findings.
2. Delete the merged package branches, worktrees first, branches
   second: git refuses to delete a branch that is still checked out in
   a worktree. Every merged tip is reachable from the target, so
   `git branch -d` succeeds; read a refusal precisely: `used by
   worktree` means step 1 left the worktree behind and says nothing
   about merge state, while `not fully merged` is evidence the package
   never actually merged. Either way investigate; `-D` answers neither.
3. Account for the rest of this round's residue from the manifest:
   round directory, package branches, any merge-target branch this
   round created, the merge tab and its root pane, any workspace this
   round created, and worktree parent directories. A `round-workspace`
   event means the round made the workspace (step 3): once the merge
   tab is closed and every remaining pane in it holds only an idle
   shell (`herdr pane process-info`), `herdr workspace close <id>`.
   A workspace inherited from `$HERDR_WORKSPACE_ID` has no such event
   and is the user's; never close it. Leave the merge target in
   place; it is the round's output. Append a `state` event per
   disposition for every resource except the round directory, while
   the manifest still exists.
4. Final report: the merge target branch, then per package: branch,
   slot and the candidate that actually did it (with any fallback
   noted), correction cycles used, quick-check evidence; plus anything
   dropped, and a per-slot summary of which candidates were used and
   which failed. Build every item except the round directory from the
   still-live manifest as one of `removed`, `retained(<reason>)`, or
   `cleanup_failed(<error>)`. Archive the round directory before you
   delete it: it is the only record of the verdicts, suite reports and
   carry-forward items the report summarises, and the report is a
   digest of them, not a substitute. The archive is a resource like
   any other and follows the write-ahead rule of step 4; the round
   directory itself gets no `state` event. Its path embeds the
   `round_id`, so two rounds can never share one, and it lives in the
   XDG state directory, which cache cleaning leaves alone:

   ```bash
   archive_dir="${XDG_STATE_HOME:-$HOME/.local/state}/herdr-fleet-<round-slug>-<round_id>"
   ```

   Append `intent` for it (`resource_key` `round/archive`, `kind`
   `dir`, `role` `round-archive`, `cleanup_policy` `report-only`,
   `parent_key` the round directory's key, `selector` that absolute
   path), `mkdir -p` the state directory (it is the user's, not a
   round resource), then `mkdir` (not `mkdir -p`) the archive
   directory, append `created` with the path in `observed`, and,
   since `report-only` keeps it by design, a `state` event with
   `status` `retained`. An "already exists" refusal is this round's
   own earlier attempt only if the manifest already holds that
   `created` event; otherwise stop and report rather than sync into
   a directory the round cannot prove it owns. Then copy
   unconditionally, in its own command:

   ```bash
   rsync -a --delete --checksum "${recorded_round_dir:?}/" "${archive_dir:?}/"
   ```

   Never put the copy behind an existence test (an earlier attempt's
   copy at the archive path must be overwritten, not taken as done)
   and never chain the copy and the delete in one command: a
   `test -e … || cp …; rm -rf …` line whose guard skips the copy
   still runs the delete, and a live round lost its entire ledger,
   every verdict and every suite report to exactly that. Prove parity
   before deleting: the copy exited 0, and a dry run of the same
   command exits 0 and prints nothing:

   ```bash
   rsync -a --delete --checksum --dry-run --itemize-changes "${recorded_round_dir:?}/" "${archive_dir:?}/"
   ```

   `--checksum` compares content, so a same-size same-mtime stale
   file cannot pass as current. Read both exit statuses directly, not
   through a pipeline. Also require the last line of `manifest.jsonl`
   in both places to carry the same `seq` and this round's
   `round_id`. On any failure append a `state` event for the archive
   with `status` `failed`, keep the round directory, and report
   `cleanup_failed(<error>)` with the archive path. Only then delete
   the round directory last, in its own command, using only the exact
   absolute path recorded on its `created` event:
   `rm -rf "${recorded_round_dir:?}"`, after confirming that path
   still matches the recorded id and that
   `<recorded_round_dir>/manifest.jsonl` carries the `round_id` of
   the round being reclaimed. Do not reconstruct the path from
   `$TMPDIR` and the slug. The `:?` guard keeps an unset recorded
   path from aiming the delete at `/`. It names repo internals and
   has served its purpose. Observe that outcome and fold it into the
   report, naming the archive path; there is no post-delete append.
   What happens to the target branch next is the user's call.

Round invariants: four roles and no more, each on a named slot whose
candidates carry auto mode, with the orchestrator the only agent the
user talks to; implementation (conflict resolution included) belongs
to implementer agents and diff-grading to reviewer agents on a
different vendor's model; builds, tests and worktree preparation are
check scripts the orchestrator runs in check panes, and broad codebase
reading is a scout's job, never the orchestrator's window; review,
quick check, and merge bind to the same exact clean commit; a blocking
finding is cleared by a fix or a reviewer verdict, never by
orchestrator reclassification, and correction counters only go up;
exactly one heavy build runs at a time; a dead model is replaced from
the slot's next candidate and recorded, never retried; the round ends
on a local branch and publishing stays with the user; a worktree
holding dirty or unmerged work stays in place; a finished agent
session closes before its package or merge task is considered done; a
container root pane is never closed explicitly (step 9) and a
workspace the round did not create is never closed at all (step 10);
resources except the round directory and the pre-ledger ones are
write-ahead (step 4) and only manifest-confirmed ones are reclaimed;
the round directory is archived to a `round_id`-unique path in the
state directory and checksum-verified before it is deleted (step 10);
the orchestrator ends a turn only at the points section 2 names, and
never on a plan or a promise.
