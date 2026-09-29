---
name: herdr-fleet
description: "Run one round of parallel implementation across multiple CLI coding agents (claude, codex, grok, agy, droid, …) in herdr-managed git worktrees, one package per worktree, merged back into one local branch. Models are picked per role through named slots backed by a model catalog with fallback. Invoke with /herdr-fleet followed by tasks or a backlog description."
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
| Implementer | `smol` / `default` / `slow` / `hard` by package difficulty; `ui` for UI packages; `slow` for merge-suite fixes | its own worktree, or the main checkout in the merge tab | nothing | commits plus a summary file |
| Reviewer | `review`; an adjudicator tries `slow` first (step 7) | nothing (read-only) | nothing | a structured verdict file |
| Scout | `smol` | nothing (read-only) | nothing | a structured report file: codebase survey (step 3) or triage of a log, manifest or listing (step 4) |

Builds, tests and worktree preparation are commands the orchestrator
runs in dedicated shell panes (steps 4, 8, 9), not agents. Conflict
resolution and merge-suite fixes are the Implementer role working in
the merge tab (step 9); grading those fixes is the Reviewer role.

Models are declared once, by name, in a **model catalog**. A model
entry names its **vendor** and lists its **providers** in order: each
provider is an agent kind plus the exact arguments that select that
model, its reasoning level and its auto-approving mode through that
CLI. One model often has several providers (the same Gemini through
`agy` or through `droid`), and quotas are per provider, so a model is
only unavailable once all its providers are. A **slot** is an ordered
list of model names. Arguments live only in the catalog; slots,
briefs and the manifest refer to models by name:

| Slot | Used for |
|---|---|
| `smol` | scouts; mechanical, well-bounded packages |
| `default` | ordinary packages |
| `slow` | foundational, concurrent, security-sensitive or data-model packages; merge-suite fixes; adjudicating re-grades |
| `hard` | optional: the rare package that is beyond `slow` (a novel algorithm, a cross-cutting change with an unsettled design, a bug with no reproduction); the most capable and most expensive models, never assigned by default |
| `ui` | optional: UI packages (step 5), in place of the slot their grade maps to; the models the user trusts most with frontend work |
| `review` | reviewers by default; a reviewer never shares a vendor with the implementer it grades |

The catalog and the slot table are the user's, not the skill's: read
both from `${XDG_CONFIG_HOME:-$HOME/.config}/herdr-fleet/slots.yml`.
Its shape, with example values:

```yaml
models:
  claude-opus-5:
    vendor: anthropic
    providers:
      - { kind: claude, args: "--dangerously-skip-permissions --model claude-opus-5" }
  claude-haiku-4.5:
    vendor: anthropic
    providers:
      - { kind: claude, args: "--dangerously-skip-permissions --model claude-haiku-4-5-20251001" }
  gpt-6-astra-medium:
    vendor: openai
    providers:
      - { kind: codex, args: "--dangerously-bypass-approvals-and-sandbox -m gpt-6-astra -c model_reasoning_effort=medium" }
      - { kind: omp,   args: "--approval-mode=yolo --model openai-codex/gpt-6-astra" }
  gpt-6-astra-xhigh:
    vendor: openai
    providers:
      - { kind: codex, args: "--dangerously-bypass-approvals-and-sandbox -m gpt-6-astra -c model_reasoning_effort=xhigh" }
  claude-fable-5.1-xhigh:
    vendor: anthropic
    providers:
      - { kind: claude, args: "--dangerously-skip-permissions --model claude-fable-5-1 --effort xhigh" }
  gemini-3.8-flash:
    vendor: google
    providers:
      - { kind: agy,   args: "--dangerously-skip-permissions --model gemini-3.8-flash --effort low" }
      - { kind: droid, args: "--auto high" }
  grok-4.6:
    vendor: xai
    providers:
      - { kind: grok,  args: "--permission-mode bypassPermissions --model grok-4.6" }
slots:
  smol:    [gemini-3.8-flash, claude-haiku-4.5]
  default: [gpt-6-astra-medium, claude-opus-5]
  slow:    [gpt-6-astra-xhigh, claude-opus-5]
  hard:    [claude-fable-5.1-xhigh, gpt-6-astra-xhigh]
  ui:      [claude-opus-5]
  review:  [grok-4.6, claude-opus-5]
```

`vendor` is required on every model and is the only thing the
cross-vendor rule compares; a CLI's name says nothing about who
serves the model (`omp` and `droid` front other vendors' models).
Providers of one model must select the same model, so a provider
without a model argument (`droid` takes its model from its own
config) belongs to a model entry only when that config matches. If
the file is missing, ask the user once which models they have,
through which CLIs, and which slot each should serve, and write the
file for them before continuing. Per-kind arguments that turn on
auto-approving mode and select the model, as verified against the
installed CLIs, with the name each kind's herdr integration goes by:

| kind | binary | integration target | auto mode | model / reasoning |
|---|---|---|---|---|
| claude | `claude` | `claude` | `--dangerously-skip-permissions` | `--model <m>`, `--effort <level>` |
| codex | `codex` | `codex` | `--dangerously-bypass-approvals-and-sandbox` (never a sandbox) | `-m <m> -c model_reasoning_effort=<low\|medium\|high\|xhigh>` |
| cursor | `cursor-agent` | `cursor` | `--yolo --trust` | `--model <m>` |
| grok | `grok` | `grok` | `--permission-mode bypassPermissions` | `--model <m>`, `--reasoning-effort <e>` |
| agy | `agy` | `antigravity-cli` | `--dangerously-skip-permissions` | `--model <m> --effort <low\|medium\|high>` |
| droid | `droid` | `droid` | `--auto high` | model from droid's own config |
| devin | `devin` | `devin` | `--permission-mode dangerous` | `--model <m>` |
| omp | `omp` | `omp` | `--approval-mode=yolo` | `--model <m>` |

Every provider carries its auto-mode argument: a fleet agent that
stops at an approval prompt stalls its package until the watch loop
notices. The arguments go after `--` on every start, pasted in as
the catalog's literal words (shell discipline, section 2):

```bash
herdr agent start <name> --kind <kind> --pane <pane-id> -- <provider-args>
```

**Slot resolution** happens once per round, in step 2: a provider
whose binary is missing (`command -v <binary>`) or whose herdr
integration cannot be brought to `current` is dropped for the round,
a model with no surviving provider is dropped with it, and the first
surviving model with its first surviving provider is the slot's
**active pair**. There is no probing beyond that. A pair that turns
out to be dead at runtime (quota, outage, bad model name) is handled
by the **slot fallback** rule in step 6, which moves first to the
same model's next provider and only then to the slot's next model;
the slot's pointer stays moved for the rest of the round. The active
pair per slot is shown in the step 3 plan and recorded in the
manifest; every fallback is recorded too, so the final report can say
which model, through which CLI, actually did each package.

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
- The main repo's working tree must be clean; surface a dirty tree
  instead of working around it.
- `python3 --version` reports 3.9 or later: the ledger script (step 3)
  needs it. Without one, say so and stop.
- Resolve the slots (step 1): `smol`, `default`, `slow` and `review`
  are required; `hard` and `ui` are optional. When `hard` is absent or
  empty no package may be graded `hard` this round; when `ui` is, UI
  packages run on the slot their grade maps to. For each provider of each
  model in each slot, in order, take the three names from the kind
  table and use each once: `command -v <binary>`; the `<integration
  target>` row of `herdr integration status` (the command takes no
  argument and lists every target); later, `herdr agent start --kind
  <kind>`. A provider fails only when that binary is missing or that
  status row cannot be brought to `current`. The two rows whose names
  differ:
  - `agy`: `command -v agy`, status row `antigravity-cli`, `--kind agy`
  - `cursor`: `command -v cursor-agent`, status row `cursor`, `--kind cursor`

  The watch loop's state detection comes from that integration. A
  row that reads `not installed` or `outdated` needs `herdr
  integration install
  <target>`, which rewrites that CLI's persistent configuration for
  every later session, not just this round: collect those targets,
  ask the user once before installing any of them, and name them in
  the final report (step 10) as kept, since an integration is the
  user's environment, not a round resource. A target the user
  declines is a failed check. Drop providers that fail either check
  and models left without one. A required slot with no surviving
  model stops the round here: report it and ask the user; a `hard`
  or `ui` slot left with none is reported and treated as absent. Then check
  the cross-vendor rule is satisfiable: for the active model of each
  implementer slot (`smol`, `default`, `slow`, and `hard` and `ui`
  when present) there must be at least
  one surviving `review` model of a different vendor; if any lacks
  one, stop and ask the user for another review model.
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

**Shell discipline.** Every tool call starts a fresh shell: variables
do not survive from one call to the next, and neither does the
working directory you think you are in. So every `git` command you
run carries `-C <main-repo-path>` or `-C <worktree-path>`, every
path in a command is the absolute path recorded in the manifest,
written out literally, and a value a command needs is assigned and
used inside that same command or pasted in as a literal. A snippet
below that shows `<placeholder>` means the literal recorded value.
Your tool calls may run in zsh, which leaves an unquoted `$var` as
one word, so a placeholder that stands for several words, above all
`<provider-args>`, is pasted as those literal words: a provider's
`args` passed through a variable reach the CLI as a single argument,
and the start fails.

**Turn discipline.** The round runs unattended and the user is not
watching in real time, so end a turn only at these points: the plan
and worktree-disposition confirmation (step 3), the post-drop
confirmation (step 7), an agent question that needs the user's
authority or an exhausted slot (step 6), a merge-target suite failure
the round cannot resolve (step 9), the final report (step 10), and
every other point where this skill says to ask or tell the user and
wait: a missing slot file (step 1), an integration install or a slot
with no surviving model (step 2), a leftover worktree or round
directory to decide on (step 3), a `GENUINE` preparation failure
(step 4), a second vanish, an implementer whose fallback leaves no
cross-vendor review model, an adjudicator or replacement reviewer
with no model left (steps 6 and 7), a third rejecting verdict
(step 7), and a third merge rejection or an unresolvable conflict
(step 9). Nothing else ends a turn: not "waiting for the agents", not a long
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
source and logs out of it: scouts return summaries; implementers end
with a summary file whose first line you read (step 5); verdicts are
read through `jq` for their decision and blocking findings (step 7);
check reports are read for their first line (step 8); pane output is
read only for agents that are `blocked`, `unknown`, suspiciously
long in `working`, or suspected of a dead model (step 6); and failing
output travels to an implementer as a file path, never as pasted
text. Anything longer than a screen that you would otherwise read to
reach a conclusion (a failing log, a leftover round's manifest, a
long worktree inventory) goes to a **triage scout** (step 4) that
returns the conclusion. Read a file in full only when a decision
genuinely turns on its contents and it is short.

## 3. Package the work

**Anchor the repo first.** The three commands that establish the
main repo are the only git commands of the round without a recorded
path to carry, so give them the repo path the user named or, failing
that, your session's working directory, explicitly: record the main
repo's absolute path (`git -C <repo-path-as-given> rev-parse
--show-toplevel`), then, with that recorded path, the current branch
(`git -C <main-repo-path> rev-parse --abbrev-ref HEAD`) and its head
sha (`git -C <main-repo-path> rev-parse HEAD`). Every later `git -C`,
every merge brief and the collision check below use that recorded
path, and the sha becomes the round's base.

**Name the round and open the ledger next**, before any scout or
workspace exists, so that everything the round creates is
write-ahead. Give the round a short kebab-case **round-slug**, and
later each package its own slug. herdr agent names are 1 to 32
characters, start with a lowercase letter, and contain only lowercase
letters, digits, `-` and `_`; the longest derived names are
`<round-slug>-suite-review` and `<slug>-merge-review`, so keep the
round-slug and every package slug to 19 characters. The package
slug names everything the package owns: branch `feat/<slug>`,
worktree label, implementer `<slug>`, reviewer `<slug>-review`,
adjudicator `<slug>-adjudicate`, merge implementer `<slug>-merge`,
merge reviewer `<slug>-merge-review`, check pane, summary and brief
files, so `herdr agent list` reads as a status board. The round-slug
names the survey scouts `<round-slug>-scout-<n>`, the triage scout
`<round-slug>-triage` (step 4), the suite-fix pair
`<round-slug>-suite-fix` and `<round-slug>-suite-review` (step 9),
the round directory, the merge tab and, when the round needs a fresh
merge target, that branch (below). Agent names are server-global and
branches already live in the repo: check `herdr agent list` and
`git -C <main-repo-path> branch --list "feat/*"` for collisions now,
the round-slug branch included, and pick a different slug rather than
debug ambiguous targets mid-round.

Resolve `"${TMPDIR:?}/herdr-fleet-<round-slug>"` to an absolute path
(the `:?` fails closed if `TMPDIR` is unset). If that path already
exists, it is an interrupted round's ledger: recover it in step 10
rather than adopting it, and pick a new slug if it remains. Only once
the path does not exist, `mkdir` (not `mkdir -p`) so a race still
fails, and immediately append `created` for the round directory
(`kind` `dir`, `role` `round-dir`, `cleanup_policy`
`delete-on-success`) with that resolved absolute path in `selector`
and `observed` to `<round-dir>/manifest.jsonl`, the round's
append-only JSONL **manifest**. The round directory is the ledger's
home, so it is the one resource that cannot be preceded by its own
`intent`. Every later reference to the round directory uses this
recorded path, never a second `$TMPDIR` resolve. Mint a `round_id`
unique to this invocation; ownership is proved by `round_id`, not by
round-slug or label.

A mutable row cannot be write-ahead, so the manifest is an event log:
an `intent` event before each create command; a `created` event
immediately after a successful response, before doing anything else;
a `state` event on every disposition; a `slot` event on every slot
resolution and fallback. Every resource but the round directory
follows that write-ahead, including every agent, pane, tab, branch,
container root pane, worktree and the workspace the round creates for
itself; a package workspace is made by `herdr worktree create` and is
recorded on its worktree's `created` event (step 4), not as a
resource of its own. An unrecorded resource cannot be reclaimed.

**Every event goes through the ledger script**, `scripts/ledger.py`
beside this SKILL.md: `<skill-dir>` below is the directory this file
was loaded from, written out literally like every other path. The
script is the manifest's only writer. It locks the file, assigns the
monotonic `seq` an auditor uses to detect a truncated or misordered
append, fills the round fields from the first record, checks every
enum, and refuses what the write-ahead rule forbids (a `created`
with no pending `intent`, a replacement's `intent` while the old one
is still live), naming the fix; a refusal appends nothing. `created`
and `state` events inherit `kind`, `role`, `parent_key`,
`cleanup_policy` and `selector` from the resource's earlier events,
and a `state` event its `observed` too, so they carry only what
changed. The round directory's event opens the manifest:

```bash
python3 <skill-dir>/scripts/ledger.py <recorded-round-dir>/manifest.jsonl created round/dir --kind dir --role round-dir --policy delete-on-success --selector path=<recorded-round-dir> --observed path=<recorded-round-dir> --round-id <round_id> --round-slug <round-slug>
```

Every later event has the same form, with `--round-id` and
`--round-slug` dropped:

```bash
python3 <skill-dir>/scripts/ledger.py <recorded-round-dir>/manifest.jsonl intent package/<slug>/worktree --kind worktree --role package-container --policy remove-when-merged --selector label=<slug>
python3 <skill-dir>/scripts/ledger.py <recorded-round-dir>/manifest.jsonl created package/<slug>/worktree --observed path=<worktree-path> --observed workspace_id=<workspace-id>
python3 <skill-dir>/scripts/ledger.py <recorded-round-dir>/manifest.jsonl state package/<slug>/branch --status live --observed accepted_sha=<sha>
```

`--selector` and `--observed` take `key=value` and repeat, and a
dotted key nests (`--observed replaced.model=<model>`); `--parent`
sets `parent_key` and `--detail` the reason. Each write-ahead
instruction in this skill names the `kind`, `role` and
`cleanup_policy` that become those flags. A replacement started in
the same pane (a restart or a slot fallback) keeps the resource's
key: a `state` event with `removed` or `failed` closes the old agent,
then a fresh `intent` and `created` record the new one. Each line the
script writes is one record:

```json
{
  "schema_version": 3,
  "round_id": "<unique per invocation>",
  "round_slug": "<slug>",
  "seq": 1,
  "event": "intent | created | state | slot",
  "resource_key": "package/<slug>/worktree",
  "kind": "worktree | workspace | tab | pane | agent | branch | dir | slot",
  "role": "package-container | package-implementer | package-reviewer | check-pane | review-pane | scout-container | scout | merge-container | merge-implementer | merge-implementer-pane | merge-reviewer | merge-reviewer-pane | merge-check-pane | package-branch | round-dir | round-workspace | merge-target | round-archive | container-root-pane | slot",
  "parent_key": "<logical parent resource_key or null>",
  "cleanup_policy": "remove-when-merged | close-aux | close-container | delete-on-success | report-only",
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
`created`. Agent `created` events also carry `slot`, `model`,
`provider_kind` and `args` in `observed`, so the report can name the
model behind every package. A `slot` event's key is `slot/<name>`
(the script fills its `kind`, `role` and `cleanup_policy`), and its
`observed` carries `model`, `provider_kind` and `args` and, on a
fallback, the pair it replaced and why under `replaced.`. The `args`
value is one quoted word here, since it is data, not a command line:

```bash
python3 <skill-dir>/scripts/ledger.py <recorded-round-dir>/manifest.jsonl slot slot/<name> --observed model=<model> --observed provider_kind=<kind> --observed 'args=<provider-args>'
```

Append one now per slot for the active pairs resolved in step 2.

Now fix the round's **base** and **merge target** from the main repo's
current branch:

- Take the main repo's absolute path, current branch and head sha
  recorded at the start of this step. The sha is the round's base:
  every worktree gets pinned to it (step 4) and the plan table
  (below) shows it.
- Record the orchestrator workspace id (step 2). Inside herdr, take
  it from `printf '%s\n' "$HERDR_WORKSPACE_ID"`. Outside herdr,
  write-ahead a workspace (`kind` `workspace`, `role`
  `round-workspace`, `cleanup_policy` `close-container`), create it,
  and read `.result.workspace.workspace_id` from the JSON for the
  `created` event:

  ```bash
  herdr workspace create --cwd <main-repo-path> --label <round-slug> --no-focus
  ```

  That recorded orchestrator workspace id is what later binds the
  scout tabs (below) and the merge tab (step 9) to this workspace;
  the globally active workspace is not a substitute. A round-created
  workspace is closed in step 10; its initial tab and root pane stay
  untouched, the round only adds tabs to it. A workspace inherited
  from `$HERDR_WORKSPACE_ID` gets no event and is never closed.
- If the current branch is shared and long-lived (the default branch,
  `develop`, `release/*`), or HEAD is detached (`--abbrev-ref` prints
  the literal `HEAD`), the round must not land on it directly: the
  merge target is a new local branch `feat/<round-slug>` created from
  the base sha at merge time (step 9). Otherwise the current branch
  itself is the merge target. Borderline cases are your judgment call.

**Understand the request** the way you would in any session: read
the user's description, the repo's convention files, the file tree,
and `git -C <main-repo-path> log`, and open the specific files a
slicing decision hinges on. Do not walk the codebase yourself. Every question that needs
broad reading goes to a **scout**: the host's own read-only subagent
facility if it has one (an Explore-style agent), otherwise a herdr
agent on the `smol` slot's active pair, in a tab of its own in the
orchestrator workspace. Write-ahead the tab (`kind` `tab`, `role`
`scout-container`, `cleanup_policy` `close-container`), its root pane
(`role` `container-root-pane`) and the agent (`role` `scout`,
`cleanup_policy` `close-aux`), then:

```bash
herdr tab create --workspace <orchestrator-workspace-id> --cwd <main-repo-path> --label <round-slug>-scout-<n> --no-focus
herdr agent start <round-slug>-scout-<n> --kind <kind> --pane <root-pane-id> -- <smol-provider-args>
```

Several scouts may run at once, each on one narrow question; they
read, so they never contend for build caches. A scout's brief is a
file-drop (step 5) and carries: the question; the rule that it edits
nothing, runs no build and no tests, and spawns nothing; and the
output contract, a report at `<recorded-round-dir>/scout-<n>.md`
with fixed sections and only the path as the reply. Scouts are fleet
agents: wait on them as on any other, `herdr agent wait
<round-slug>-scout-<n> --timeout 540000` for one, the step 6 wait
block for several, then read the report file; a scout that settles
without its report is re-prompted (the swallowed-prompt trap, step
6), and one that fails on its model follows the slot fallback there.
The report a
round always needs, once per requested task: the files it will
touch, its overlap with the other tasks, a difficulty grade with
reasons, and the convention files, glossary and design specs the
implementer must read, by path. And once per repo: the
dependency-resolution command, any large ignored build artifacts a
worktree will need, the build command, and the per-package
quick-check command, which feed steps 4 and 8. When a report leaves a
slicing decision open, ask that scout a follow-up in its pane rather
than reading the code yourself. When a report contradicts the user's
request (the feature already exists, the named module is gone, the
task is far larger than described), put the contradiction in the
plan table below and let the user decide; do not silently re-scope.
Survey scouts are shut and their tabs closed (step 9 shutdown
procedure) right after the plan is confirmed, and also when the user
rejects the plan, which ends the round at step 10. The triage scout
of step 4 is a different, round-long agent.

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
- Keep UI work in packages of its own, apart from the logic and data
  behind it, so a UI package (step 5) is UI all the way through.
- Write down, per package: scope, acceptance criteria, the design or
  spec references the agent must read, a difficulty grade, whether it
  is a UI package, and the slot these map to (step 5).

Inventory the source repo's existing worktrees: detached or prunable
entries, a target path occupied by a different branch, checkouts whose
herdr workspace closed while the directory remains, and prior rounds'
disk cost:

```bash
herdr worktree list --cwd <main-repo-path>
git -C <main-repo-path> worktree list --porcelain
```

List read-only and ask the user to decide reuse / remove / keep for
each; never auto-clean a prior round's resources. When the listings
run past a screen, a scout (above) builds the table (path, branch,
dirty or clean, herdr workspace still open, disk size) and you
present it; the decisions stay with the user.

Present the plan as a short table and get one confirmation before
creating anything else (skip only if the user already said to run
unattended): packages, branch names, merge order, merge target, slot
per package (a `hard` package always with the reason it is beyond
`slow`, since that slot spends the most expensive models; unattended
runs never assign `hard` on their own), the active pair per slot from
step 2, any scout contradictions, and those worktree decisions. The
user may override slots here ("this round, codex only", "this round,
`slow` runs on gpt-6-astra-xhigh only"): apply the override by filtering the slot's
models or by replacing its list with other catalog models, never by
editing the slot file or inventing a model the catalog lacks; a
replacement passes the same step 2 checks (binary, integration,
cross-vendor review), and each slot that changed gets a `slot` event.

## 4. One worktree per package

Before each `herdr worktree create`, append `intent` for the worktree
(`package/<slug>/worktree`, `kind` `worktree`, `role`
`package-container`, `cleanup_policy` `remove-when-merged`), its
branch (`package/<slug>/branch`, `kind` `branch`, `role`
`package-branch`, `cleanup_policy` `remove-when-merged`), and its
container root pane (`role` `container-root-pane`, `cleanup_policy`
`close-container`).

```bash
herdr worktree create --cwd <main-repo-path> --branch feat/<slug> --base <sha> --label <slug> --no-focus
```

Pin every package to the same `--base` commit (the round's base sha
from step 3): it keeps packages from drifting apart if the branch
moves mid-round, and every later verification diffs against it.

Append `created` for all three from the JSON (workspace id, root pane
id, and path on the worktree and container-root-pane; branch ref).
The worktree's parent directory is the user's, shared with other
checkouts; the round neither records nor removes it. Reviewers (step
7) and quick checks (step 8) need the worktree path.

**Prepare the worktree yourself, in a check pane.** The worktree still
has to be made buildable before an implementer starts in it. Right
after the worktree's `created` events, split a **check pane** off the
root pane, write-ahead it (`role` `check-pane`, `kind` `pane`,
`cleanup_policy` `close-aux`), and read the new pane id from the
JSON. `--direction` is required; `down` suits the usual wide root
pane, `right` a tall one (`herdr pane layout` shows which):

```bash
herdr pane split <root-pane-id> --direction down --cwd <worktree-path> --no-focus
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
run so neither a stale marker nor a stale report from a previous run
can ever be taken for this one:

```bash
#!/usr/bin/env bash
set -o pipefail
log="<recorded-round-dir>/<slug>-<phase>-<sha>-<attempt>.log"
report="<recorded-round-dir>/<slug>-<phase>-<sha>-<attempt>.md"
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
herdr pane wait-output <check-pane-id> --source recent-unwrapped --match "FLEET <slug> <phase> <sha> <attempt> exit=" --timeout 540000
head -n 1 <recorded-round-dir>/<slug>-<phase>-<sha>-<attempt>.md
```

`--source recent-unwrapped` is required: the default `recent`
snapshot keeps soft wraps, and a marker that wraps in a narrow pane
never matches as a substring. Keep `--timeout` under the tool call's
own limit. When the wait expires before the marker appears, find out
why before waiting again: `herdr pane process-info --pane
<check-pane-id>`. A foreground process other than the shell means
the script is still running, so re-issue the same `wait-output` (it
searches output already on screen, so a marker printed in between is
still caught). An idle shell with no marker means the script died
before printing it: treat that run as `FAIL`, rerun once with the
next attempt number, and send a second death to the triage scout
with the log path.

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

You never read a failing log yourself. A `FAIL` report goes to the
**triage scout**, `<round-slug>-triage`: one read-only agent for the
whole round, started exactly like a step 3 scout (its own tab in the
orchestrator workspace, write-ahead, the `smol` slot's active pair)
the first time a report needs it, and kept: every later report is a
fresh file-drop prompt to the same agent, waited on with `herdr agent
wait` as in step 3. It is shut, tab included, in step 10, or earlier
only when it vanishes or loses its model (step 6 traps), in which
case the next report starts it again. It never touches a worktree.
Each prompt carries one report path and one question, and names the
answer file, one per report so answers never overwrite each other:
`<recorded-round-dir>/triage-<slug>-<phase>-<sha>-<attempt>.md`,
with a fixed first line, `TRANSIENT`, `GENUINE` or `MISCONFIGURED`,
followed by the failing command, the decisive lines of the log quoted
by line number, and, for `MISCONFIGURED`, the corrected command.
`TRANSIENT` (network, a cache lock, a flaky download) is a rerun with
the next attempt number. `MISCONFIGURED` on preparation is evidence
against the scout report, not against the worktree: take the
corrected command and rerun. `GENUINE` on preparation means the repo
does not build at the base sha; stop and tell the user.
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
renames) go to `smol`. Everything else is `default`. When unsure
between those three, assign up. `hard` is never reached by assigning
up: it is for the rare package that `slow` is expected to fail at (a
novel algorithm, a cross-cutting change whose design is still open, a
bug with no reproduction), and only when the user asked for it or the
plan table named the package as `hard` with its reason and the user
confirmed. The models there are the most expensive in the catalog,
so a `hard` package is one the round would otherwise have to drop.

A **UI package** is one whose deliverable is user-facing UI/UX:
components, layout, styling, interaction, motion, visual
accessibility. When the `ui` slot is present, a UI package graded
`smol`, `default` or `slow` runs on `ui`; a `hard` one stays on
`hard`. The grade is still recorded and still drives the brief: the
`smol` rules below follow the grade, not the slot.

Write-ahead the implementer (`kind` `agent`, `role`
`package-implementer`, slot name in `selector`) and append `created`,
with the pair actually used, after a successful start:

```bash
herdr agent start <slug> --kind <kind> --pane <root-pane-id> -- <provider-args>
```

A start that returns anything but success may still have left an
agent behind: `agent_not_ready` means the CLI came up but stopped at
a dialog, and a timeout means it may still be coming up. This holds
for every `agent start` in the round. Before anything else, check
`herdr agent list` for that exact name in that pane; if it is there,
append `created` with the observed ids, then handle its screen as a
`blocked` agent (step 6) or exit it. Only when no agent by that name
exists may the start be retried. An agent that exists without a
`created` event is one the cleanup of step 10 cannot reclaim.

A real brief is too long to push through a terminal. Write it as a
Markdown file, one per package, in the recorded round directory. One
brief per package at `<recorded-round-dir>/<slug>.md`; prompt with a
one-liner:

```bash
herdr agent prompt <slug> "Read <recorded-round-dir>/<slug>.md and complete the package it describes. Summary file for this turn: <recorded-round-dir>/<slug>-summary-1.md"
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
- For a package graded `smol` only: the work is strictly mechanical. Where a
  step needs a judgment call the brief did not make, stop, commit what
  is done, and report the question instead of guessing.
- Commit discipline: Conventional Commits, imperative lowercase subject
  ≤72 chars, no Co-Authored-By trailers or generation watermarks.
  Commit on the package branch. Do not push.
- **End-of-turn contract**: at the end of every turn, write the
  summary file named in the prompt that started that turn, whose
  first line is exactly `DONE` or `QUESTION`, followed by a summary
  of changes with file references, anything skipped or uncertain,
  and, after `QUESTION`, the question itself; reply with only the
  path. Every prompt you send an implementer (the first one, a
  send-back, an answer, a re-brief after a restart or fallback) names
  a fresh path, `<recorded-round-dir>/<agent-name>-summary-<n>.md`
  with `<n>` counted up per prompt, so a stale summary from an
  earlier turn can never be read as this one's. You read the first
  line on every settle (step 6): a `QUESTION` package does not enter
  the gates, costs no correction cycle, and gets its answer from the
  brief's context if that decides it, otherwise from the user; a
  missing file at the path the last prompt named is a swallowed
  contract, re-prompt for it. Merge implementers (step 9) follow the
  same contract under their own agent names; their conclusion still
  comes from git and the merge reviewer's verdict, the summary only
  carries `DONE`, `QUESTION` and the notes.

## 6. Watch the round: this is your job now

Between briefing and the final merge, the orchestrator's whole job is
the watch loop; the wait block and the traps below serve every fleet
agent, the scouts of steps 3 and 4 and the merge agents of step 9
included. Do not end the turn to "wait for the agents", and do
not drift into side work; an unwatched fleet stalls: a `blocked` agent
burns wall-clock until someone answers it, and a crashed agent
silently drops its package.

Loop until every package has **concluded**: passed review (step 7)
and its quick checks (step 8), or been dropped. Settled is not
concluded: review findings and failing output send an agent back to
`working`, and its package re-enters the loop. Sleep-polling burns a
tool call a minute to hear "no change"; block on the fleet instead.
`herdr agent wait` returns the moment an agent reaches `idle`,
`done`, or `blocked`, and costs nothing while it waits, and
`herdr pane wait-output` does the same for a check script's marker:

```bash
bash -c '
for a in <unsettled agent names>; do herdr agent wait "$a" --timeout 540000 & done
<for the check script in flight, if any:> herdr pane wait-output <check-pane-id> --source recent-unwrapped --match "<its marker prefix>" --timeout 540000 &
wait -n; kill $(jobs -p) 2>/dev/null'
herdr agent list | jq -c '[.result.agents[] | {name, agent_status, pane_id}]'
```

Wake on the first event, sweep with that projected `herdr agent
list` (the full listing carries session ids, titles and paths for
every agent, a page of context per wake that the loop never needs;
the sweep is named there in the rest of this section), act, then
block again on whatever is still unsettled. Details that keep the
block safe, verified against a live fleet:

- Run the block under a bash ≥ 4.3: `wait -n` is a bash-ism that
  macOS's stock bash 3.2 predates, and zsh or fish error out and leak
  the background waits. Check once with
  `bash -c 'echo ${BASH_VERSINFO[0]}'`; without a modern bash, wait on
  one agent at a time and lean on the timeout sweep.
- Never run the block with nothing to wait on: with no background
  job `wait -n` returns at once and the loop spins. When the only
  unsettled work is a check script, the block is that single
  `pane wait-output`; when nothing at all is in flight, the round has
  either concluded or lost track, so sweep and reconcile the status
  board instead of blocking.
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

Keep a per-package status board (agent state, last state change,
slot and pair in use, restarts used, `candidate_sha`, `accepted_sha`,
correction cycles used, quick-check state, next action) as a file at
`<recorded-round-dir>/status.md`, rewritten on every wake, so it
survives context compaction. After a compaction, recover the loop
from that file, the manifest, and a fresh `herdr agent list` sweep,
and continue the round rather than ending the turn; a long session is
not a reason to stop.

What to read on a wake depends on the state. A settled implementer's
decisions come from git and the first line of the summary file its
last prompt named (step 5), not from its pane. Read pane output only for an agent that is
`blocked`, `unknown`, `working` with no change across several sweeps,
or settled without producing what its contract requires, and then
the visible screen first:

```bash
herdr agent read <name> --source visible
```

Priorities inside the loop: answer `blocked` agents first (each is
stalled wall-clock), then act on settled ones (a settled implementer
with `DONE` gets its candidate recorded, its quick check queued, and a
reviewer dispatched; one with `QUESTION` gets its answer; a settled
reviewer gets its verdict read, step 7; a finished check gets its
report's first line read, step 8), then check long-`working` ones: an
agent whose output hasn't changed across several sweeps may be stuck
on an unrecognized prompt or spinning; read the screen and decide.
Surface progress to the user at transitions that matter (package
settled, review sent, quick checks passed, merge landed), not on
every wake.

Known traps and how to handle them:

- **Slot fallback.** An agent that reaches `blocked`, `idle` or `done`
  moments after a start or a prompt, with no work done, and whose
  visible screen names a quota, usage or rate limit, an overloaded or
  unavailable model, an unknown model name, an expired login, or an
  HTTP 401/429/5xx, has lost its model, not its task. Exit the agent
  only: its exit command through the pane as in the step 9 procedure,
  confirm the name is gone from `herdr agent list` and that
  `herdr pane process-info` shows the pane back at an idle shell, and
  do not close the pane, since the replacement reuses it. Mark the
  failed pair for the rest of the round: the provider for that model
  when the screen blames the model (quota for it, unknown name,
  overloaded), or the provider's kind for every model when it blames
  the CLI itself (expired login, subscription exhausted). Take the
  next surviving pair: the same model's next provider first, then the
  slot's next model. For any agent in a reviewer role (`<slug>-review`,
  `<slug>-adjudicate`, `<slug>-merge-review`, `<round-slug>-suite-review`),
  whatever slot it runs on, skip every model whose vendor equals that
  of the implementer it grades; the vendor rule follows the role, not
  the slot name. An adjudicator's candidate list is the `slow` slot
  followed by the `review` slot (step 7), so it is exhausted only when
  both are. Append a `slot` event naming the old and new pair, start
  the replacement in the same pane with the new kind and arguments,
  write-ahead and `created` as usual, and re-brief it by role, with
  the original brief path in every case: an implementer is told to
  read `git log <base-sha>..HEAD` and `git status` in its checkout
  first and continue from the committed state, and gets the next
  summary path (step 5); a reviewer or adjudicator is told to grade
  the same recorded candidate sha afresh and write the same verdict
  path; a scout is told to answer the same question afresh to the
  same report path. Every later start on that slot uses the new pair
  directly; a failed pair is never retried this round. An exhausted
  `ui` slot hands each of its packages to the slot its grade maps to,
  with a `slot` event and the implementer re-brief above. Any other
  slot whose pairs are exhausted ends the turn with the question, after doing
  everything on this wake that does not depend on it.
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
  provider's `args` in the catalog for the rest of the round. A
  question that needs new authority or a user decision goes to the
  user instead of being answered on their behalf. When that happens,
  first do everything on this wake that does not depend on the answer
  (answer the other blocked agents, record settled candidates, queue
  checks, dispatch reviewers), then end the turn with the question and
  the current status board rather than blocking on `herdr agent wait`
  again. The fleet keeps working in herdr while the user answers; on
  the reply, resume with a `herdr agent list` sweep. Do not answer on
  the user's behalf, and do not hold the question for hours behind
  another wait.
- **Alternate-screen output is unrecoverable.** Agents that render on
  the terminal's alternate screen never feed scrolled-off rows into
  herdr's scrollback, so raising `--lines` cannot recover a long
  finished reply. When a read comes back truncated, ask the agent to
  write its complete report to a Markdown file in the round directory
  and reply with only the path, then read the file directly.
- **A vanished agent is not a finished agent.** If a name disappears
  from `herdr agent list` and the pane is back at a shell, the agent
  exited or crashed. Check `git -C <worktree-path> log` for what
  actually landed, then `herdr agent start` a fresh agent in the same
  pane, on the same pair, and re-brief it by role as in the slot
  fallback above. Budget one such restart per package: a second vanish on
  the same pair is a dead pair, handled by the slot fallback above,
  and a vanish after that goes to the user with the status board.
- Never send a new prompt to a `working` agent: it lands mid-turn and
  corrupts the run. Wait for `idle`/`done`/`blocked`.

## 7. Review each package with a dedicated reviewer agent

When an implementer settles with `DONE`, first check the plumbing
yourself; this is cheap metadata, not source.
`git -C <worktree-path> log --oneline <base-sha>..HEAD` is the
complete set of commits the package produced, taken from git, never
from the agent's summary. Require
`git -C <worktree-path> status --porcelain` to be empty, then record
`candidate_sha=$(git -C <worktree-path> rev-parse HEAD)`. Uncommitted
leftovers mean the brief was not followed and cannot enter either
gate. An empty range means the package produced nothing: re-brief or
drop it; an empty branch has nothing to merge and never reaches
step 9.

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
`accepted_sha`, both on the status board and as a `state` event on
`package/<slug>/branch` carrying the sha, so a recovery from the
manifest alone can prove what was accepted.

Hand the diff to a **reviewer agent**, a fleet agent of its own on the
`review` slot, in its own pane, and do not grade it yourself. Package
diffs pulled into the orchestrator are exactly the source this
architecture keeps out: by the fourth package your judgment is
swimming in the first three's implementation noise, and having briefed
the round you also want it to succeed; a reviewer that wrote none of
it, on a different vendor's model, grades without that bias. The
reviewer's pair is the first `review` model, in slot order, whose
vendor differs from the vendor of this package's implementer (the
one that actually ran, after any fallback), with its first surviving
provider; the step 2 check guarantees one exists for the active
implementer models, and a package whose implementer fell back to a
model no `review` model differs from goes to the user. Split a review
pane off the package's root pane, write-ahead the pane and the
reviewer agent (`role` `review-pane` / `package-reviewer`, `kind`
`pane` / `agent`, `cleanup_policy` `close-aux`), read the new pane id
from the JSON, and start it:

```bash
herdr pane split <root-pane-id> --direction down --cwd <worktree-path> --no-focus
herdr agent start <slug>-review --kind <kind> --pane <new-pane-id> -- <review-provider-args>
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
  `<recorded-round-dir>/<slug>-verdict-<candidate_sha>.json`, every
  key present even when empty:

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
      "assumption": "<the unvalidated shared assumption, or null with status not-applicable>",
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
available. If no such assumption is found, `assumption` is `null`,
`status` is `not-applicable`, and `external_evidence` documents the
candidates examined and the evidence that validates them, or why none
applies; the reviewer must not invent one to fill the field, and the
validation below rejects any other combination of a null assumption
with a status.
Missing evidence alone is not a proven defect; any resulting finding
is classified by the priority rules above. Checks requiring execution
go through a check pane within the round's serial queue; the design
itself grants no execution authority. Re-grades revisit this analysis
for the new candidate and may carry it forward only with an explicit
explanation of why it remains applicable.

Reviewers are fleet agents: the same watch loop, wait block, states,
and traps apply, and a settled reviewer means a verdict file to read.
Reviews run no builds, so any number of reviewers can work while
implementers are still working; the one-heavy-build rule is untouched.
Read a verdict for its decision, not its prose, and validate it
before you read it, because a projection that tolerates missing or
misspelled fields would show a broken verdict as "no blocking
findings". First the validation, which exits non-zero on any
violation:

```bash
jq -e '(.candidate_sha | type == "string") and (.overall_correctness | IN("correct", "incorrect")) and (.findings | type == "array") and all(.findings[]; (.priority | IN("P0", "P1", "P2", "P3")) and (.title | type == "string") and (.file_path | type == "string") and (.line_start | type == "number")) and (.assumption_check | type == "object") and (.assumption_check.status | IN("designed", "executed", "not-applicable")) and ((.overall_correctness == "incorrect") == any(.findings[]; .priority == "P0" or .priority == "P1")) and (.assumption_check.assumption != null or .assumption_check.status == "not-applicable")' <verdict-path> >/dev/null
```

Then, only after it exits 0 and `candidate_sha` equals the recorded
one, the projection:

```bash
jq '{candidate_sha, overall_correctness, blocking: [.findings[] | select(.priority == "P0" or .priority == "P1") | {title, priority, file_path, line_start}], assumption: (.assumption_check | {status, assumption})}' <verdict-path>
```

A verdict that is missing, that `jq` cannot parse, that fails the
validation, or that names a sha other than the recorded one is not a
verdict: send it back to the reviewer for correction, at no
correction-cycle cost. A second malformed verdict from the same
reviewer replaces that reviewer for this package only: a model that
writes bad JSON is alive, so its pair is not marked failed for the
round. Exit the agent as in the slot fallback (step 6), keep the
pane, start `<slug>-review` again on the next `review` model that
satisfies the vendor rule, append a `slot` event whose detail names
the malformed output and this package, and brief it afresh; with no
such model left, the package goes to the user. The projection
above is all of the verdict you read; the titles and locations are
enough to route it, and the bodies stay in the file for the
implementer.

You adjudicate. With both gates' results in hand, decide accept, send
back, or drop; that call needs round-level context (merge order,
budgets, how the packages interact) that only you hold. Send-back is
a short prompt: the verdict file's path, the check report's path and
its triage file's path if it failed, the next summary path (step 5),
and the instruction to fix every P0 and P1 there and any P2 worth
taking; do not restate the findings. A blocking finding is
cleared by a fix or by a reviewer verdict; reclassifying it yourself
is how a round quietly ships a rejected package. When a re-grade
surfaces a likely-blocking issue that sat unchanged in the prior
candidate, hand that one finding to an **adjudicator**,
`<slug>-adjudicate`, a second reviewer agent (write-ahead `role`
`package-reviewer`, in a pane split like the review pane) on the
first `slow` model, in slot order, whose vendor differs from the
package's implementer, or, when none does, on the next `review`
model that does; with no such model left, the finding goes to the
user. The vendor rule applies to the adjudicator on every start and
fallback exactly as to any reviewer (step 6). Its verdict uses the
same format and settles that finding.

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
inspect (its work exists nowhere else; append a `state` event with
`status` `retained` and the reason) but every agent named for it
closes at the drop. An accepted package's sessions close immediately
once both gates have passed and `accepted_sha` is recorded. Shut each
agent and close the review pane(s) and the check pane with the
shutdown procedure in step 9; the package is not concluded until
every agent name it owns (`<slug>`, `<slug>-review`,
`<slug>-adjudicate` if started) is gone from `herdr agent list` and
every auxiliary pane is closed. Merge-target work uses fresh agents
instead of keeping package sessions alive.

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
`git -C <worktree-path> status --porcelain` to be empty and both
`git -C <worktree-path> rev-parse HEAD` and
`git -C <worktree-path> rev-parse feat/<slug>` to equal the recorded
`candidate_sha`; this binds the tested tree to the same commit the
reviewer grades.

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
gate. `FAIL <candidate_sha>` goes to the triage scout (step 4):
`TRANSIENT` is a rerun on the same candidate; `GENUINE` or
`MISCONFIGURED` goes into the send-back of step 7 as the report
file's path plus the triage file's path, never as pasted output, and
any retained fix, mechanical or otherwise, is a new candidate for
both gates. A report naming any other sha is discarded and the check
rerun. No changed tree reaches the merge without a matching verdict
and a green check report on its exact sha.

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
checkout as cwd. A conflict-merge implementer (`<slug>-merge`, item
2) runs on the slot of the package whose merge it resolves (`default`
at least, never `smol`); the suite-fix implementer
(`<round-slug>-suite-fix`, item 3) runs on `slow`, since a failure
that only appears when the packages meet is foundational by
definition. A merge reviewer's pair (`<slug>-merge-review` or
`<round-slug>-suite-review`) is chosen as in step 7 against the
vendor of the implementer it grades. Each merge agent's pane gets its
own write-ahead role (`merge-implementer-pane`, `merge-reviewer-pane`,
`kind` `pane`, `cleanup_policy` `close-aux`) beside the agent's
(`merge-implementer`, `merge-reviewer`, `kind` `agent`,
`cleanup_policy` `close-aux`). Every merge-review brief and verdict carries
the same format and the correlated-failure requirement from step 7,
applied to the combined behavior under review. Merge-phase fixes
share one budget of 2 correction cycles for the whole merge target,
counted like step 7's: each rejecting merge verdict and each `FAIL`
of the suite after a fix increments it, and a third goes to the user
with the report paths.

1. Re-check the main repo: the tree still clean
   (`git -C <main-repo-path> status --porcelain`) and HEAD still on
   the branch recorded in step 3
   (`git -C <main-repo-path> rev-parse --abbrev-ref HEAD`), or, when
   the recorded branch is the literal `HEAD` of a detached checkout,
   `git -C <main-repo-path> rev-parse HEAD` still equal to the base
   sha, since `--abbrev-ref` prints `HEAD` for any detached commit
   and would pass a moved checkout; hours may
   have passed, and uncommitted edits or a mid-round branch switch
   would ride into the merges; surface a mismatch and go to step 10
   instead of working around it. If the recorded branch itself is the
   merge target, require
   `git -C <main-repo-path> merge-base --is-ancestor <base-sha> HEAD`;
   a failure means the branch was reset or rewritten, so go to step
   10 instead of merging packages based on stale history. A branch
   that moved forward while retaining the base may still merge;
   report it. Then check out the merge target: if step 3 chose a
   fresh target, write-ahead the branch (`kind` `branch`, `role`
   `merge-target`, `cleanup_policy` `report-only`) and create it now
   with `git -C <main-repo-path> switch -c feat/<round-slug> <base-sha>`;
   an "already exists" refusal means the step-3 collision check was
   dodged, so go to step 10 and surface it. Otherwise stay on the
   recorded branch.
2. Merge the accepted package branches in the agreed order, one at a
   time. Immediately before each merge, require the package worktree
   to be clean and `git -C <worktree-path> rev-parse feat/<slug>` to
   equal its `accepted_sha`, record
   `pre_merge_sha=$(git -C <main-repo-path> rev-parse HEAD)`, then run
   `git -C <main-repo-path> merge --no-ff feat/<slug>`. A clean merge
   is bookkeeping and yours to run; it gets no review. A conflicted
   merge is implementation in the main checkout, not the package
   worktree. Split a pane off the merge tab's root pane; write-ahead
   the pane (`role` `merge-implementer-pane`) and the agent (`role`
   `merge-implementer`):

   ```bash
   herdr pane split <merge-root-pane-id> --direction down --cwd <main-repo-path> --no-focus
   herdr agent start <slug>-merge --kind <kind> --pane <new-pane-id> -- <provider-args>
   ```

   Brief it by file-drop to resolve and commit the merge, with the
   package brief's path for intent and the summary path of step 5.
   Do not reuse the worktree-rooted
   implementer: a path written in a brief does not change a live
   agent's cwd, and the conflict index (`MERGE_HEAD`) exists only in
   the main checkout. Exactly one agent may write the main checkout at
   a time. Once it settles, require a clean committed merge, record
   `candidate_sha=$(git -C <main-repo-path> rev-parse HEAD)`, and
   dispatch `<slug>-merge-review` in another pane split the same way
   off the merge tab's root (write-ahead `role` `merge-reviewer-pane`
   / `merge-reviewer`) to
   grade `git diff <pre_merge_sha> <candidate_sha>` read-only,
   concentrating on the conflict resolution and combined behavior.
   Accept only a verdict naming that candidate sha with no blocking
   finding. Start the next merge only after this review passes and
   the pair is shut (shutdown procedure below). A conflict the round
   cannot resolve (the implementer settles with `QUESTION` or is
   blocked on a user decision, a rejecting verdict spends the merge
   budget, or a merge reviewer has no model left) must not leave the
   checkout mid-merge: shut the pair, then
   `git -C <main-repo-path> merge --abort`, require HEAD to equal
   `pre_merge_sha` and the tree to be clean, append a `state` event
   on `package/<slug>/branch` with `status` `retained` and the
   conflicting files as detail, and go to step 10, where the report
   names the branch and the conflict; the package's worktree and
   branch stay in place, and no later package merges after it this
   round.
3. Run the repo's full build and test suite on the merge target as a
   check script in the merge check pane (`<slug>` the round-slug,
   `<phase>` `suite`, `<sha>` the merge target's current sha): the
   round's heavy build, and the first time the packages meet, so
   cross-package failures land here. Its commands are the full build
   and test commands from the scout report (step 3); it changes no
   code and makes no commits. The suite binds to its sha exactly as a
   quick check does (step 8): before running and again after the
   marker appears, require `git -C <main-repo-path> status
   --porcelain` to be empty and both `git -C <main-repo-path>
   rev-parse HEAD` and `git -C <main-repo-path> rev-parse
   <merge-target>` to equal the sha the script names. While the suite
   runs, nothing else touches the main checkout: no merge implementer
   is live and you run no git there. When the marker appears, run the
   post-run binding, then read the report's first line; three
   outcomes follow.
   `PASS` with a clean post-run binding is a green suite.
   `PASS` with a dirty tree is not a pass: a build that mutates
   tracked files has produced an unverified tree. This path bypasses
   the triage scout, since the log shows nothing wrong: write
   `git -C <main-repo-path> status --porcelain` to
   `<recorded-round-dir>/<round-slug>-suite-<sha>-<attempt>-dirty.md`
   and hand that path to the suite-fix implementer below, which
   decides whether those files are generated output to commit or a
   build to fix; the rerun binds to the new sha.
   `FAIL` goes to the triage scout (step 4): `TRANSIENT` is a rerun
   on the same sha; otherwise the report path and the triage file's
   path go to the suite-fix implementer below.
   The suite-fix implementer is `<round-slug>-suite-fix`, on the
   `slow` slot's active pair, split and written ahead as in item 2
   with the roles named above, rooted in the main checkout; the pairs
   of item 2 are already shut by now, so it is always a fresh start.
   Record `pre_fix_sha=$(git -C <main-repo-path> rev-parse HEAD)`,
   brief it by file-drop with the paths above and the summary path
   of step 5, and once it settles require a clean tree and a new
   commit, record
   `candidate_sha=$(git -C <main-repo-path> rev-parse HEAD)`, then
   dispatch `<round-slug>-suite-review` (as in item 2) to grade the
   exact `git diff <pre_fix_sha> <candidate_sha>` read-only. Accept
   only a verdict naming that candidate sha with no blocking finding
   and, after the pair is shut (shutdown procedure below), run the
   suite script again on the new sha with the next attempt number.
   Handle one implementer/reviewer pair at a time. If the suite-fix
   implementer is blocked on a user decision, the merge budget is
   spent, or the failure cannot be resolved this round, keep the
   failing report, leave the merge-target red-suite fix state
   untouched, and go to step 10.

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
alive, and `herdr tab close` reclaims the merge tab's root. A scout
tab (step 3) closes the same way once its agent is gone. When merge
work is finished, close the merge tab:

```bash
herdr tab close <merge-tab-id>
```

That close is the safety net for any auxiliary pane the prompt closes
missed. Everything the round produced now lives on the merge target;
anything needed after cleanup is a fresh agent's job there.

## 10. Clean up and report

Run this step when merge work finishes, when this round stops after
the round directory exists (a rejected plan in step 3 included), and
when a later invocation finds a leftover round directory (step 3),
and consume that manifest. A leftover from another invocation needs
the user's decision before anything is destroyed; this round's own
abort does not. Shut still-live agents and auxiliary panes with the
step 9 procedure first, the triage scout excepted (it is the last to
go, below), then close still-live survey-scout tabs and the merge
tab with `herdr tab close <tab-id>`. Do not wait for a green suite to
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

The reconciliation itself is reading, and for a leftover round from
another invocation it is a lot of it: the triage scout (step 4; start
it now if none is live) reads that manifest, `herdr agent list`,
`herdr worktree list` and the branch list, and returns one table at
`<recorded-round-dir>/triage-reconcile-<n>.md`, one row per recorded
resource: key, role, cleanup policy, recorded id, whether it is live,
its occupant or git state, and the last recorded status. You decide
each disposition from the table. The table is evidence for deciding,
not for destroying: before any remove, close or delete below, re-run
the specific check that step names (`git status --porcelain`, the sha
comparisons, `herdr pane process-info`) yourself on that one
resource; a scout's row never substitutes for it. Once the table is
read and every disposition below is decided, the triage scout is done
for the round: shut it and close its tab with the step 9 procedure
before item 3, whose workspace close requires every round tab gone.

1. Per package, remove the worktree only when all of these hold:
   `git -C <worktree-path> status --porcelain` is empty, the branch
   tip equals the `accepted_sha` recorded on the branch's `state`
   event, `git -C <main-repo-path> merge-base --is-ancestor
   <accepted_sha> <merge-target>` passes, every agent the package
   owned is gone, and every auxiliary pane is already closed. Leave
   the container root pane in place. Enumerate the workspace's
   remaining panes (the recorded root pane included) and confirm via
   `herdr pane process-info --pane <pane-id>` that each holds only an
   idle shell; herdr shuts down the workspace's terminal runtimes
   before a forced removal, so a vanished agent does not make
   `--force` safe. Fail closed on any non-shell occupant, user
   takeover, or unidentifiable state; retain and report. Only then
   `herdr worktree remove --workspace <id> --force`. A dirty or
   unmerged worktree stays in place for inspection. A dropped
   package's worktree (its commits exist nowhere else) never gets
   force-removed; surface it instead. Do not touch the worktrees'
   parent directory and do not `git worktree prune`; at most
   `git -C <main-repo-path> worktree prune --dry-run --verbose` and
   report the findings.
2. Delete the merged package branches, worktrees first, branches
   second: git refuses to delete a branch that is still checked out in
   a worktree. Every merged tip is reachable from the target, so
   `git -C <main-repo-path> branch -d feat/<slug>` succeeds; read a
   refusal precisely: `used by worktree` means step 1 left the
   worktree behind and says nothing about merge state, while `not
   fully merged` is evidence the package never actually merged. Either
   way investigate; `-D` answers neither.
3. Account for the rest of this round's residue from the manifest:
   round directory, package branches, any merge-target branch this
   round created, the scout tabs, the merge tab and its root pane,
   and the orchestrator workspace if this round created it (package
   workspaces went with their worktrees in item 1 and are never
   closed on their own). A `round-workspace` event
   means the round made the workspace (step 3): once every tab the
   round added is closed and every remaining pane in it holds only an
   idle shell (`herdr pane process-info`), `herdr workspace close
   <id>`. A workspace inherited from `$HERDR_WORKSPACE_ID` has no such
   event and is the user's; never close it. Leave the merge target in
   place; it is the round's output. Append a `state` event per
   disposition for every resource except the round directory, while
   the manifest still exists.
4. Final report: the merge target branch, then per package: branch,
   slot and the model and CLI that actually did it (with any fallback
   or restart noted), correction cycles used, quick-check evidence,
   and the reviewer's `assumption_check` status with the assumption
   in one line; plus anything dropped, a per-slot summary of which
   pairs were used and which failed, any integration the round
   installed in step 2 (kept), and the merge budget used. Build
   every item except the round directory from the still-live manifest
   as one of `removed`, `retained(<reason>)`, or
   `cleanup_failed(<error>)`. Archive the round directory before you
   delete it: it is the only record of the verdicts, suite reports and
   carry-forward items the report summarises, and the report is a
   digest of them, not a substitute. The archive is a resource like
   any other and follows the write-ahead rule of step 3; the round
   directory itself gets no `state` event. Its path embeds the
   `round_id`, so two rounds can never share one, and it lives under
   the skill's own directory in the XDG state directory, which cache
   cleaning leaves alone:

   ```
   ${XDG_STATE_HOME:-$HOME/.local/state}/herdr-fleet/<round-slug>-<round_id>
   ```

   Resolve that to an absolute path once and paste the literal into
   every command below; per the shell discipline of step 2 a variable
   would be empty in the next call, and an empty source or target
   aims `rsync --delete` or `rm -rf` at the wrong tree. Append
   `intent` for it (`resource_key` `round/archive`, `kind` `dir`,
   `role` `round-archive`, `cleanup_policy` `report-only`,
   `parent_key` the round directory's key, `selector` that absolute
   path), `mkdir -p` the `herdr-fleet` state directory (it is the
   user's, not a round resource), then `mkdir` (not `mkdir -p`) the
   archive directory, append `created` with the path in `observed`,
   and, since `report-only` keeps it by design, a `state` event with
   `status` `retained`. An "already exists" refusal is this round's
   own earlier attempt only if the manifest already holds that
   `created` event; otherwise stop and report rather than sync into
   a directory the round cannot prove it owns. Then copy
   unconditionally, in its own command, both paths literal and both
   ending in `/`:

   ```bash
   rsync -a --delete --checksum "<recorded-round-dir>/" "<archive-dir>/"
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
   rsync -a --delete --checksum --dry-run --itemize-changes "<recorded-round-dir>/" "<archive-dir>/"
   ```

   `--checksum` compares content, so a same-size same-mtime stale
   file cannot pass as current. Read both exit statuses directly, not
   through a pipeline. Also require the last line of `manifest.jsonl`
   in both places to carry the same `seq` and this round's
   `round_id`. On any failure append a `state` event for the archive
   with `status` `failed`, keep the round directory, and report
   `cleanup_failed(<error>)` with the archive path. Only then delete
   the round directory last, in its own command, with the literal
   absolute path recorded on its `created` event:
   `rm -rf "<recorded-round-dir>"`, after confirming that path still
   matches the recorded id and that
   `<recorded-round-dir>/manifest.jsonl` carries the `round_id` of
   the round being reclaimed. Do not reconstruct the path from
   `$TMPDIR` and the slug, and never write the delete with a
   variable. It names repo internals and has served its purpose.
   Observe that outcome and fold it into the report, naming the
   archive path; there is no post-delete append. What happens to the
   target branch next is the user's call.

Round invariants: four roles and no more, each on a named slot whose
providers carry auto mode, with the orchestrator the only agent the
user talks to; implementation (conflict resolution included) belongs
to implementer agents and diff-grading to reviewer agents on a
different vendor's model, chosen per package; builds, tests and
worktree preparation are check scripts the orchestrator runs in check
panes, and broad codebase reading and the triage of logs, leftover
manifests and long listings are a scout's job, never the
orchestrator's window; every git command names its repo with `-C`
and every destructive path is a recorded literal; review, quick
check, and merge bind to the same exact clean commit; a blocking
finding is cleared by a fix or a reviewer verdict, never by
orchestrator reclassification, and correction counters, package and
merge alike, only go up; exactly one heavy build runs at a time; a
dead pair is replaced from the slot's next pair and recorded, never
retried, a reviewer that writes malformed verdicts is replaced for
its package rather than retired, and a package restarts a vanished
agent at most once; a conflicted merge the round cannot resolve is
aborted, never left half-done; the
round ends on a local branch and publishing stays with the user; a
worktree holding dirty or unmerged work stays in place; a finished
agent session closes before its package or merge task is considered
done; a container root pane is never closed explicitly (step 9) and
a workspace the round did not create is never closed at all (step
10); every resource but the round directory is write-ahead (step 3),
every manifest event is appended by the ledger script, and only
manifest-confirmed resources are reclaimed; the round directory
is archived to a `round_id`-unique path in the state directory and
checksum-verified before it is deleted (step 10); the orchestrator
ends a turn only at the points section 2 names, and never on a plan
or a promise.
