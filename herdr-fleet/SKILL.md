---
name: herdr-fleet
description: "Run one round of parallel implementation across multiple CLI coding agents (claude, codex, grok, agy, droid, …) in herdr-managed git worktrees, one package per worktree, merged back into one local branch. Models are picked per role through named slots backed by a model catalog with fallback. Invoke with /herdr-fleet followed by tasks or a backlog description."
disable-model-invocation: true
---

# herdr-fleet

Complete several work packages in parallel: each package gets a git
worktree and a CLI coding agent inside herdr, and the accepted packages
merge into one local branch. You are the **orchestrator**, the only
agent the user talks to. You plan, brief, decide and report. You never
implement a package and never grade a diff: implementation belongs to
**implementer** agents in their own worktrees, grading to **reviewer**
agents on a different vendor's model. Every fleet agent runs in an
auto-approving mode, so approval questions reach the user through you
alone.

The bookkeeping lives in one script, `scripts/fleet.py` beside this
file: herdr calls, the write-ahead ledger, sha binding, the serial
check queue, review briefs, verdict validation, merging and cleanup.
Each command prints a short result meant to be read whole; act on what
it prints. Everything you write by hand is a decision: the plan, the
briefs, answers to agents, accept/send-back/drop, the report.

## 1. Roles and slots

| Role | Runs on | Writes | Hands back |
|---|---|---|---|
| Orchestrator | the user's session | the plan, briefs, answers | the final report |
| Implementer | `smol` / `default` / `slow` / `hard` by difficulty, `ui` for UI packages | its own worktree, or the merge worktree | commits plus a summary file |
| Reviewer | `review` (an adjudicator tries `slow` first) | nothing | a verdict file |

A **slot** is an ordered list of models from the user's catalog,
`${XDG_CONFIG_HOME:-$HOME/.config}/herdr-fleet/slots.yml`. Each model
names its vendor and its providers (an agent kind plus the exact
arguments selecting the model and its auto-approving mode). `smol`,
`default`, `slow` and `review` are required; `hard` and `ui` are
optional. A reviewer never shares a vendor with the implementer it
grades; fleet.py enforces that on every start and fallback. When
`init` reports that the catalog is missing or malformed, read
[references/slots.md](references/slots.md), ask the user once which
models and CLIs they have, and write the file for them.

Builds, tests and dependency installs are **checks**: commands
fleet.py runs detached, one at a time across the whole round, bound to
an exact commit. Implementers never run the heavy build or suite,
because parallel builds fight over shared caches.

## 2. Start the round

Pick a short round slug (lowercase, at most 19 characters; it names the
merge branch `feat/<round-slug>`), then:

```bash
python3 <skill-dir>/scripts/fleet.py init --repo <repo-path> --slug <round-slug>
```

`<skill-dir>` is the directory this file was loaded from, written out
literally. `init` records the repo, its current branch and head sha
(the round's **base**), creates the round directory and its ledger,
resolves every slot to its first usable model and CLI, and prints the
command prefix for the rest of the round, `fleet: python3 … --round
<dir>`. Every later command in this skill is that prefix, written `F`
below, pasted literally at the start of each command line (zsh does
not word-split a variable holding it). Act on what `init` prints:

- `BLOCKER` lines: a required slot with no usable model, or no review
  model of another vendor. Ask the user.
- A CLI whose herdr integration is not `current`: `herdr integration
  install <target>` rewrites that CLI's user config, so list the
  targets, ask the user once, install the approved ones, then
  `F resolve`. A declined target leaves its providers out.
- `leftover round with open resources`: read
  [references/recovery.md](references/recovery.md) and let the user
  decide before anything of it is touched.
- A note that the main checkout has uncommitted changes needs no
  action: worktrees start from the base commit, and the main checkout
  stays the user's for the whole round.

**Turn discipline.** The round runs unattended. End a turn only to get
the plan confirmed (step 3), for a decision that needs the user's
authority, when a slot or budget is exhausted, for an unresolvable
conflict or red suite, and for the final report. Waiting for agents is
never a reason to end a turn: `F wait` is the waiting. Before ending
any turn, read your last paragraph; if it announces work ("next I'll
merge…"), do that work now.

## 3. Plan the packages

Understand the request the way you would in any session: the user's
description, the repo's convention files (CLAUDE.md, AGENTS.md), the
file tree, `git -C <repo> log`, and the specific files a slicing
decision turns on. For broad reading, use your host's read-only
subagent (an Explore-style agent) and keep its conclusions, not the
source. Run nothing from the repo yourself; you need three commands
from it, as the repo documents them:

- **prep**: dependency resolution for a fresh worktree (`pnpm install`,
  `uv sync`), plus any large ignored artifact to copy from the main
  repo (`--copy <relative-path>`). Many repos need none.
- **check**: the package's own fast verification (it compiles, its
  tests pass), never the full suite.
- **suite**: the repo's full build and test, run once on the merge
  target.

**Contradictions.** Compare the tasks with each other, not only with
the code. Two tasks that set the same behaviour to different values
(two default orders, two formats for one output, one removing what
another extends) cannot both land. Package neither; put the choices
(one, the other, or both behind a switch) in the plan, and in an
unattended round in the final report. Tasks that contradict the repo
(the feature already exists, the module is gone) go in the plan the
same way. The other tasks go ahead.

**Slicing.** Parallel wall-clock is the point, so slice aggressively
and serialize only what truly depends on another package's output:

- One package, one branch, one agent, small enough for one sitting.
- Minimal file overlap; where two packages must share a file, fix
  their merge order now.
- UI work in packages of its own, apart from the logic behind it.
- Per package: a slug (lowercase, at most 19 characters), scope,
  acceptance criteria, the specs to read, and a grade:
  - `smol`: mechanical and well bounded (a pattern applied, a rename);
  - `default`: ordinary work;
  - `slow`: foundational, concurrent, security-sensitive or data-model
    work, anything other packages build on; when unsure, grade up;
  - `hard`: only when the user asks for it or confirms it with a reason
    `slow` would fail (a novel algorithm, an unsettled cross-cutting
    design); never assigned on your own in an unattended round.

  A UI package runs on `ui` when that slot exists (a `hard` one stays
  on `hard`); its grade still drives the brief.

Present the plan as one short table and get one confirmation (skip it
when the user said to run unattended): packages with slot and grade,
merge order, the active model per slot from `init`, the three commands,
and any contradictions. Say that each CLI may ask to trust the
worktree directories the round creates, and that the round accepts
those folder-only trusts; the confirmation is the authority for that
and nothing wider. A per-round slot override ("only codex this round")
is `F resolve --override <slot>=<model>,<model>` with catalog model
names, one `--override` per slot; the user's file stays untouched.

## 4. Packages and briefs

For each package, in merge order:

```bash
F package <slug> --slot <slot> [--grade <grade>] [--prep '<cmd>'] [--copy <rel>]... [--check '<cmd>']
```

It creates the worktree on `feat/<slug>` from the base and queues the
prep. Then write the brief to `<round-dir>/<slug>.md` and start the
implementer:

```bash
F implement <slug> --brief <round-dir>/<slug>.md
```

The prompt it sends points at the brief and at
`<round-dir>/implementer-rules.md`, which fleet.py writes: work only in
this worktree, write tests but run no heavy build, commit with the
repo's convention and no trailers, never push or rewrite, and end every
turn with a summary file whose first line is `DONE` or `QUESTION`. The
brief carries what only you know, self-contained and referencing code
by path:

- scope and acceptance criteria;
- the convention files, glossary and specs to read first;
- for a `smol` package: the work is strictly mechanical; where a step
  needs a judgment call the brief did not make, commit what is done and
  end with `QUESTION`.

A brief written while the prep runs is held and sent when the prep
passes. A start that fails prints why and the screen; a missing or
broken CLI or model is a fallback (step 5).

## 5. Watch the round

Between briefing and merging, your whole job is this loop:

```bash
F wait
```

Give the Bash call a 600000 ms timeout. `wait` blocks (up to 540 s)
until something needs you, does the mechanical follow-ups itself, and
ends with a status board. When an implementer reports `DONE`, it
submits the commit as the candidate: it records the sha, dispatches a
cross-vendor reviewer and queues the package's check. When both gates
pass on the same sha, it accepts the package and stops its agents.
Read each event and act; then `F wait` again:

| Event | Action |
|---|---|
| `<name> QUESTION` | Answer from the brief's context with `F prompt <name> --text '…'`. A question that needs the user's authority goes to the user (below). |
| `<name> BLOCKED` with a screen | A trust dialog or a question UI; handle it as below. |
| settled without `DONE`/`QUESTION`, or `has not picked up its prompt` | Read the screen shown. A swallowed prompt: `F prompt <name> --resend`. A lost model: fallback. |
| a screen naming a quota, rate limit, unknown model, expired login, HTTP 401/429/5xx, or a failed start | `F fallback <name> --reason '<what the screen says>'`; add `--cli` when the CLI itself is at fault (login, subscription) rather than one model. `no model left` goes to the user; once they fix the catalog, `F resolve`, then the same fallback again. |
| `<name> VANISHED` | `F restart <name>`. A second vanish is a dead pair: fallback. |
| `<reviewer> … verdict malformed: <reason>` or `missing` | `F prompt <reviewer> --text 'Rewrite <verdict-path>: <reason>'`. A second malformed verdict from it: fallback. |
| `both gates in, … -> send-back` | `F send-back <pkg>` (it writes the feedback file and counts the cycle), or drop. |
| `check <pkg> prep … FAIL` with a log tail | A transient failure (network, cache lock) is `F recheck <pkg> --prep`; a wrong command is `F recheck <pkg> --prep '<fixed>'`; a repo that does not build at the base goes to the user. |
| `check <pkg> check … FAIL` | Part of the gate result: the send-back carries the report path. A transient failure is `F recheck <pkg>`. |
| `timeout: still working` | Wait again. An agent stuck `working` across several waits: `herdr agent read <name> --source visible`, then decide. |
| `nothing in flight` | Every package has concluded: merge (step 7). |

**Blocked screens.** Read the screen before acting. Answer a menu with
`herdr agent send-keys <name> <key>`, free text with `herdr pane
send-text <pane> '<text>'` then `herdr pane send-keys <pane> enter`.

- A folder-trust dialog for the directory the agent was started in (a
  round worktree or the main repo) is covered by the plan
  confirmation: choose the option that trusts that directory only.
- Everything else such a dialog offers (a hook, an MCP server, a tool
  permission, a settings change) belongs to the user: choose the option
  that declines or skips it for this session.
- An approval prompt means the provider's auto-mode argument is wrong:
  approve this once and tell the user to fix the catalog.
- A question that needs the user's authority: first do everything on
  this wake that does not depend on it, then end the turn with the
  question and the board. On the reply, `F wait` again.

Note every trust accepted and every item declined for the final
report.

**Alternate-screen agents** cannot replay a long scrolled-off reply;
when a read comes back truncated, ask the agent to write the full
answer to a file in the round directory and reply with the path.

## 6. Gates and budgets

A candidate is accepted only when the reviewer's verdict and the check
both pass on the same clean commit; fleet.py refuses anything else.
Your judgment sits around that:

- A blocking finding (P0/P1) is cleared by a fix or by a reviewer's
  verdict, never by your reclassification.
- Every fix is a new candidate: `wait` submits it, the check reruns in
  full, and the same reviewer re-grades against its prior verdict.
- When a re-grade raises a likely-blocking issue in code the prior
  candidate already had, hand that one finding to an adjudicator:
  `F adjudicate <pkg> --finding '<title and location>'`. Its verdict
  settles that finding.
- Each package has 2 **correction cycles**; a rejecting verdict that
  opens a send-back spends one, a check failure alone spends none. On
  the third rejection, drop the package or ask the user, then
  `F send-back <pkg> --extend`.
- `F drop <pkg> --reason '…'` stops its agents and keeps its worktree
  and branch for the user. After a drop, present the reduced package
  set and get confirmation before merging (unless the user authorized
  unattended continuation).

## 7. Merge

Once every package has been accepted or dropped:

```bash
F merge --order <slug>,<slug> --suite '<full build and test>' [--prep '<cmd>']
```

It creates the merge worktree on `feat/<round-slug>` from the base and
merges the accepted branches in order with `--no-ff`. A clean merge is
bookkeeping and gets no review. When all have merged, it queues the
suite; `F wait` reports it.

- **Conflict.** `merge` prints the conflicting files and the slot to
  use. Write a brief at `<round-dir>/<slug>-merge.md` (the package
  brief's path for intent, the conflicting files, resolve and commit
  the merge), then `F implement merge --name <slug>-merge --brief
  <file>`. `wait` submits, reviews and accepts it like a package;
  after `merge: ACCEPTED`, run `F merge` again to continue. A conflict
  the round cannot resolve (a `QUESTION` that needs the user, a spent
  budget) is `F merge --abort`: the package stays on its branch for
  the user, and no later package merges this round.
- **Red suite.** Write a brief at `<round-dir>/<round-slug>-suite-fix.md`
  with the report path from the event, then `F implement merge --name
  <round-slug>-suite-fix --slot slow --brief <file>`. `wait` reviews
  the fix and reruns the suite on it. A transient failure is
  `F recheck merge`.

The merge phase shares one budget of 2 correction cycles; a third
rejection goes to the user with the report paths.

## 8. Clean up and report

```bash
F cleanup
```

It stops every agent, removes each merged package's worktree and
branch, removes the merge worktree when the suite is green, keeps
everything else with a reason, and prints the report data. The round
directory stays as the round's record. Then write the final report:

- the merge target `feat/<round-slug>` and its suite result; when the
  user's branch (from `init`) is their own feature branch rather than
  a shared one, the command for them to run:
  `git -C <repo> merge --ff-only feat/<round-slug>` (it refuses if they
  committed there since the base);
- per package: outcome, the model and CLI that did it, fallbacks and
  restarts, correction cycles, the reviewer's assumption check;
- dropped packages and kept worktrees with their reasons;
- contradictory tasks left for the user, with the choices;
- trust dialogs accepted, and hooks, MCP servers or permissions
  declined;
- integrations installed this round (they stay installed).

Publishing (push, PR, merging into the default branch) stays with the
user.

After a context compaction, or when the round was interrupted,
`F status` restores the picture; continue from there
([references/recovery.md](references/recovery.md)).

## Invariants

- You never implement, grade, build or test; agents implement, other
  vendors review, and fleet.py runs checks one at a time.
- Review, check and merge bind to the same exact clean commit.
- The main checkout is the user's: the round only adds and removes
  worktrees and branches; all merging happens in the merge worktree,
  and no commit the round made is ever rewritten.
- Every resource the round creates goes through fleet.py, so the ledger
  can account for it; anything you create by hand is invisible to
  cleanup.
- A dirty, unmerged or dropped worktree stays in place for the user.
- The round ends on a local branch; publishing stays with the user.
