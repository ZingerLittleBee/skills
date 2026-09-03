---
name: herdr-fleet
description: "Run one round of parallel implementation across multiple CLI coding agents (claude, codex, droid, grok, …) in herdr-managed git worktrees, one package per worktree, merged back into one local branch. Invoke with /herdr-fleet followed by tasks or a backlog description."
disable-model-invocation: true
---

# herdr-fleet

Complete several work packages in parallel by giving each one a
git worktree and a dedicated CLI coding agent inside herdr. You are the
**orchestrator**: you slice the work, brief the agents, watch their state,
dispatch reviewers and checkers, and adjudicate their results. You never
implement, and you never pull package diffs into your own window —
source lives in the agents' worktrees and gets graded by dedicated
reviewer agents in their own panes (step 7), and builds and tests run
in dedicated
checker agents (steps 3, 8, 9), never in the orchestrator's window.
That split is what makes the round safe: your judgment on package N
stays sharp after babysitting packages A through M, and no two
writers ever share a checkout.

## 1. Preconditions

- Confirm you are inside a herdr-managed pane: `test "${HERDR_ENV:-}" = 1`.
  If not, say so and stop — do not drive herdr from outside herdr.
- The main repo's working tree must be clean (`git status`); surface a dirty
  tree instead of working around it.
- Check `herdr integration status`: every agent kind you plan to
  assign (reviewer and checker kinds included) needs its integration
  to read `current` — the watch loop's state detection comes from that
  integration, so run `herdr integration install <kind>` for any kind
  reading `not installed` or `outdated`. (`herdr agent` lists the
  *supported* kinds only; whether an agent binary is actually installed
  herdr cannot tell — ask the user which subscriptions to use if they
  haven't said.)
- This is a long, hands-off run. If the session isn't in an auto-accepting
  permission mode, warn that every approval prompt stalls the round.

herdr CLI basics that the whole flow relies on: control commands return
JSON — read every workspace/tab/pane id from the response
(`.result.workspace`, `.result.root_pane.pane_id`, …), never guess them.
Agent states: `working` (leave it alone), `blocked` (it needs input),
`idle`/`done` (turn finished), `unknown` (present but unclassified — not
proof of completion). A package is **settled** when its agent reads `idle`
or `done`; an `unknown` agent must be read before it counts as anything.

## 2. Package the work

Do not read the codebase yourself to slice the work. Dispatch a
read-only **survey agent** first — the host's own subagent facility
if it has one (an Explore-style read-only agent), otherwise a herdr
agent `<round-slug>-survey` started in a new tab in the orchestrator
workspace (pick the round-slug, below, before starting it):

```bash
herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd <main-repo-path> --label <round-slug>-survey --no-focus
herdr agent start <round-slug>-survey --kind <kind> --pane <root-pane-id>
```

The survey brief asks, per requested task, for the set of files it
will touch, its overlap with the other tasks, a difficulty grade with
reasons, and the convention files, glossary, and design specs the
implementer must read, by path — and once for the repo, the
dependency-resolution command, any large ignored build artifacts a
worktree will need, and the project's build and per-package test
commands, which feed steps 3 and 8. Package from that report and
adjudicate; do not re-derive the survey by reading code. If the herdr
fallback is used it is the round's only pre-ledger resource (the
round directory does not exist yet): its report is written to
`"${TMPDIR:?}/herdr-fleet-<round-slug>-survey.md"`, the agent is shut
and its tab closed (step 9 shutdown procedure) before step 3 begins,
and the report file is moved into the round directory once that
exists in step 3, so it is reclaimed with the round.

Group the requested tasks into packages that can genuinely run in
parallel — and slice aggressively: parallel wall-clock is the point of
the round, so whenever a task decomposes into independent pieces, make
each piece its own package rather than one long serial one. Serialize
only what truly depends on another package's output:

- One package = one branch = one agent. Keep each package small enough
  that a single agent finishes it in one sitting.
- Minimize file overlap between packages. Where two packages must touch the
  same file, note it as a merge risk up front and decide their merge order
  now — a shared *base* commit merges cleanly, but two packages editing
  the same lines will not.
- Write down, per package: scope, acceptance criteria, the design or spec
  references the agent must read, and a difficulty grade.

Give the round a short kebab-case **round-slug** and each package its own
slug. The package slug names everything the package owns — branch
`feat/<slug>`, worktree label, agent, checker agent `<slug>-check`,
reviewer agent `<slug>-review`, merge fixer `<slug>-merge`, merge
reviewer `<slug>-merge-review`, and brief file — so `herdr agent list`
reads as a status board; the round-slug names the survey agent
(above), the brief directory (step 5), the merge checker
`<round-slug>-check` (step 9) and, when the round needs a fresh merge
target, that branch (below). Agent names are server-global and
branches already live in the repo: check `herdr agent list` and
`git branch --list "feat/*"` for collisions now — the round-slug
branch included — and pick a different
slug rather than debug ambiguous targets mid-round. Also refuse a
round-slug whose `"${TMPDIR:?}/herdr-fleet-<round-slug>"` already
exists: that leftover is an interrupted round's ledger — recover it
in step 10 rather than adopting it; pick a new slug if it remains.

Now fix the round's **base** and **merge target** from the main repo's
current branch:

- Record the main repo's absolute path (`git rev-parse
  --show-toplevel`), the current branch (`git rev-parse --abbrev-ref
  HEAD`), and its head sha (`git rev-parse HEAD`). The sha is the
  round's base — every worktree gets pinned to it (step 3) — and the
  path is what worktree creation (step 3) and conflict briefs (step 9)
  reference; your shell's cwd hours from now is not a substitute.
- Record the orchestrator workspace id from
  `printf '%s\n' "$HERDR_WORKSPACE_ID"`. That recorded orchestrator
  workspace id is what later binds the merge tab to this workspace
  (step 9); the globally active workspace is not a substitute.
- If the current branch is shared and long-lived (the default branch,
  `develop`, `release/*`), or HEAD is detached (`--abbrev-ref` prints
  the literal `HEAD`), the round must not land on it directly: the
  merge target is a new local branch `feat/<round-slug>` created from
  the base sha at merge time (step 9). Otherwise the current branch
  itself is the merge target. Borderline cases are your judgment call.

Inventory the source repo's existing worktrees — detached or prunable
entries, a target path occupied by a different branch, checkouts whose
herdr workspace closed while the directory remains, and prior rounds'
disk cost:

```bash
herdr worktree list --cwd <main-repo-path>
git -C <main-repo-path> worktree list --porcelain
```

List read-only and ask the user to decide reuse / remove / keep for
each; never auto-clean a prior round's resources.

Present the plan — packages, branch names, merge order, merge target,
agent kind per package, and those worktree decisions — as a short table
and get one confirmation before creating anything (skip only if the
user already said to run unattended).

## 3. One worktree per package

Persist an append-only JSONL manifest at
`<round-dir>/manifest.jsonl`. The round directory is the ledger's
home, so it cannot be preceded by its own `intent`. Resolve
`"${TMPDIR:?}/herdr-fleet-<round-slug>"` to an absolute path — the
`:?` fails closed if `TMPDIR` is unset. If that path already exists,
recover it in step 10; do not `mkdir -p` and do not adopt it. Only
once the path does not exist, `mkdir` (not `mkdir -p`) so a race
still fails, and immediately append `created` for the round
directory (`kind` `dir`, `role` `round-dir`, `cleanup_policy`
`delete-on-success`) with that resolved absolute path in `selector`
and `observed` before doing anything else — step 5 reuses this
recorded path, never a second `$TMPDIR` resolve. If a herdr survey
agent left a report in `$TMPDIR` (step 2), move it into the round
directory now. Mint a `round_id` unique to this invocation;
ownership is proved by `round_id`, not by round-slug or label. `seq`
increases monotonically so an auditor can detect a truncated or
misordered append.

A mutable row cannot be write-ahead, so this is an event log: write an
`intent` event and flush it before each create command; append a
`created` event immediately after a successful response, before doing
anything else; append a `state` event on disposition. Never rewrite an
earlier line. Every later resource follows that write-ahead, including
every agent, pane, tab, branch, container root pane, and worktree
parent directory; only the round directory is created first so the
ledger can exist, and an unrecorded resource cannot be reclaimed.

Record envelope:

```json
{
  "schema_version": 1,
  "round_id": "<unique per invocation>",
  "round_slug": "<slug>",
  "seq": 1,
  "event": "intent | created | state",
  "resource_key": "package/<slug>/worktree",
  "kind": "worktree | tab | pane | agent | branch | dir",
  "role": "package-container | package-implementer | package-reviewer | package-checker | merge-container | merge-fixer | merge-reviewer | merge-checker | package-branch | round-dir | merge-target | worktree-parent-directory | container-root-pane",
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
`observed` is empty on `intent` and carries the real ids on `created`.

Before each `herdr worktree create`, append `intent` for the worktree
(`package/<slug>/worktree`, `kind` `worktree`, `role`
`package-container`, `cleanup_policy` `remove-when-merged`), its
branch (`package/<slug>/branch`, `kind` `branch`, `role`
`package-branch`), its container root pane (`role`
`container-root-pane`, `cleanup_policy` `close-container`), and
the worktree parent directory (`kind` `dir`, `role`
`worktree-parent-directory`, `cleanup_policy` `delete-on-success`).

```bash
herdr worktree create --cwd <main-repo-path> --branch feat/<slug> --base <sha> --label <slug> --no-focus
```

Pin every package to the same `--base` commit (the round's base sha from
step 2): it keeps packages from drifting apart if the branch moves
mid-round, and every later verification diffs against it.

Append `created` for all four from the JSON (workspace id, root pane
id, and path on the worktree and container-root-pane; branch ref;
parent path). Reviewers (step 7) and checkers (step 8) need the
worktree path. The worktree still has to be made buildable before an
implementer starts in it, and that preparation is the package's
**checker agent**'s job, not yours. Right after the worktree's
`created` events, split a checker pane off the root pane, write-ahead
the pane and the agent (`role` `package-checker`, `kind` `pane` /
`agent`, `cleanup_policy` `close-aux`), read the new pane id from the
JSON, and start it:

```bash
herdr pane split <root-pane-id> --cwd <worktree-path> --no-focus
herdr agent start <slug>-check --kind <kind> --pane <new-pane-id>
```

Brief it (file-drop, step 5) with a preparation brief that carries:

- **Binary artifacts don't follow.** Git worktrees share history, not
  ignored build artifacts. Name each large local artifact the build
  depends on (a prebuilt xcframework, a vendored binary — the survey
  report lists them) and have the checker copy the real directory
  from the main repo into the worktree; symlinks often defeat build
  systems that resolve artifact identity through the path.
- The project's dependency-resolution command from the survey report
  (e.g. `swift package resolve`, `pnpm install`), to run once in the
  worktree; retry on transient network failures rather than
  concluding the worktree is broken.
- No build and no test run — preparation only.
- The output contract: write a report to
  `<recorded-round-dir>/<slug>-prep.md` and reply with only the path.

Resolution contends for the same shared caches as builds, so prompt
one checker at a time and wait for it to settle before prompting the
next. Once its report is read, the checker stays idle in its pane
until step 8 needs it.

## 4. Assign agents by difficulty

Map difficulty to the user's subscriptions, strongest kind to the hardest
package. Foundational or architecturally risky packages get the strongest
agent — a weak foundation costs every reviewer and every later round.
Mechanical, well-bounded packages (apply an established pattern, styling
sweeps, copy changes) go to the cheaper kinds. When unsure, assign up.
Checker agents run commands and copy output, so the cheapest kind is
fine for them; the reviewer-kind rule in step 7 does not apply to
checkers. Write-ahead the implementer (`kind` `agent`, `role`
`package-implementer`) and append `created` after a successful start:

```bash
herdr agent start <slug> --kind <kind> --pane <root-pane-id>
```

## 5. Brief each agent

A real brief is too long to push through a terminal. Write it as a
Markdown file, one per package, in the round directory recorded on
the round-dir `created` event in step 3 — that absolute path, not a
fresh `$TMPDIR` resolve, and do not `mkdir` it again. One brief per
package at `<recorded-round-dir>/<slug>.md`; prompt with a one-liner:

```bash
herdr agent prompt <slug> "Read <recorded-round-dir>/<slug>.md and complete the package it describes."
```

Long text sent through `agent prompt` risks wrapping and paste-mode
mangling, and a file survives for re-briefing after a crash or a swallowed
prompt. This is the **file-drop** rule, and it covers everything long you
send an agent all round — briefs, review feedback, failing build output:
write a file in the round directory, send the path. Write the file with
the same discipline as a handoff document: self-contained, referencing
specs and code by path instead of inlining them, and with secrets
redacted — the agent's pane is visible to anyone at the screen.

The brief must carry:

- The package scope and acceptance criteria, plus pointers to the repo's
  convention files (CLAUDE.md / AGENTS.md), glossary, and any design specs —
  tell the agent to read them first.
- **Write tests, but do not run the heavy build or test suite.** The
  package's checker agent validates serially afterwards, one build at
  a time. Explain why in the brief: concurrent builds across worktrees
  fight over shared caches and locks and make the machine unusable, so
  a parallel round only works if exactly one build runs at a time.
- Commit discipline: Conventional Commits, imperative lowercase subject
  ≤72 chars, no Co-Authored-By trailers or generation watermarks. Commit on
  the package branch. Do not push.
- End-of-turn contract: a summary of changes with file references, and a
  list of anything skipped or uncertain.

## 6. Watch the round — this is your job now

Between briefing and the final merge, the orchestrator's whole job is
the watch loop. Do not end the turn to "wait for the agents", and do
not drift into side work — an unwatched fleet stalls: a `blocked` agent
burns wall-clock until someone answers it, and a crashed agent silently
drops its package.

Loop until every package has **concluded** — passed review (step 7) and
its quick checks (step 8), or been dropped. Settled is not concluded:
review findings and failing output send an agent back to `working`, and
its package re-enters the loop. Sleep-polling burns a tool call a
minute to hear "no change"; block on the fleet instead — `herdr agent
wait` returns the moment an agent reaches `idle`, `done`, or `blocked`,
and costs nothing while it waits:

```bash
bash -c '
for a in <unsettled agent names>; do herdr agent wait "$a" --timeout 540000 & done
wait -n; kill $(jobs -p) 2>/dev/null'
herdr agent list
```

Wake on the first event, sweep with `herdr agent list`, act, then block
again on whatever is still unsettled. Details that keep the block safe,
verified against a live fleet:

- Run the block under a bash ≥ 4.3: `wait -n` is a bash-ism that
  macOS's stock bash 3.2 predates, and zsh or fish error out and leak
  the background waits. Check once with
  `bash -c 'echo ${BASH_VERSINFO[0]}'`; without a modern bash, wait on
  one agent at a time and lean on the timeout sweep.
- Wait only on agents that are unsettled *and still listed* — a wait on
  an agent already `idle` returns in milliseconds, and a wait on a name
  that no longer exists fails just as fast with `agent_not_found`;
  either turns the block into a busy-loop. The first `agent_not_found`
  usefully wakes the loop to report a crash, but handle the vanished
  agent (see the traps below) before blocking again.
- Keep `--timeout` under this call's own command limit — raise the
  call's limit rather than shrink the wait — and treat expiry as a
  periodic sweep that catches whatever the waits miss: an agent
  vanishing mid-wait, or one stuck in `unknown`, which `herdr agent
  wait` never fires on.

Keep a per-package status board — agent state, last state change,
`candidate_sha`, `accepted_sha`, correction cycles used, quick-check
state, next action — and update it on every wake. When an agent changes state,
read its recent output before deciding anything:

```bash
herdr agent read <name> --source recent-unwrapped --lines 120
```

Priorities inside the loop: answer `blocked` agents first (each is
stalled wall-clock), then act on settled ones — a settled implementer
gets its candidate recorded, quick checks queued, and a reviewer
dispatched, a settled reviewer gets its verdict read (step 7), a
settled checker gets its report read (steps 3, 8, 9) — then check
long-`working` ones — an agent whose output hasn't changed across
several sweeps may be stuck on an unrecognized prompt or spinning;
read the pane and decide.
Surface progress to the user at transitions that matter (package settled,
review sent, quick checks passed, merge landed), not on every wake.

Known traps and how to handle them:

- **Swallowed first prompt.** Some agents (droid, notably) eat a prompt sent
  during their startup/welcome screen. If an agent is `idle` shortly after
  start with no meaningful output, re-send the pointer prompt — the brief
  file is still on disk, which is one reason it is a file.
- **`blocked`** means the agent is showing an approval or question UI. Read
  the screen before acting. For a menu, use
  `herdr agent send-keys <name> <key>`. For an in-scope free-text answer,
  use `herdr pane send-text <pane-id> <text>` followed by
  `herdr pane send-keys <pane-id> enter`; `agent prompt` rejects a blocked
  agent with `agent_blocked`. A question that needs new authority or a user
  decision goes to the user instead of being answered on their behalf.
- **Alternate-screen output is unrecoverable.** Agents that render on the
  terminal's alternate screen never feed scrolled-off rows into herdr's
  scrollback, so raising `--lines` cannot recover a long finished reply.
  When a read comes back truncated, ask the agent to write its complete
  report to a Markdown file in the round directory and reply with only
  the path, then read the file directly.
- **A vanished agent is not a finished agent.** If a name disappears from
  `herdr agent list` and the pane is back at a shell, the agent exited or
  crashed. Check `git log` in the worktree for what actually landed, then
  `herdr agent start` a fresh agent in the same pane and re-brief it with
  what is already committed.
- Never send a new prompt to a `working` agent — it lands mid-turn and
  corrupts the run. Wait for `idle`/`done`/`blocked`.

## 7. Review each package — with a dedicated reviewer agent

When an implementer settles, first check the plumbing yourself; this
is cheap metadata, not source. `git log <base-sha>..HEAD` in the worktree is
the complete set of commits the package produced — taken from git, never
from the agent's summary. Require `git status --porcelain` to be empty,
then record `candidate_sha=$(git rev-parse HEAD)`. Uncommitted leftovers
mean the brief was not followed and cannot enter either gate.
An empty range means the package produced nothing: re-brief or drop it —
an empty branch has nothing to merge and never reaches step 9.

A candidate is **qualified** by two gates, both bound to that exact
`candidate_sha`: the review gate (this step) and the quick-check gate
(step 8). Run them concurrently — reviews run no builds and grade the
diff from git objects, so neither disturbs the other — and queue the
quick checks the moment the sha is recorded. (If the project's build
mutates tracked files, let the quick checks finish before dispatching
the reviewer.) While either gate is still running, hold your feedback:
collect both gates' results and send one combined fix brief, so a
build failure and review findings cost one fix cycle, not two. Accept
only when both gates pass the same clean sha, and record it then as
`accepted_sha`. Any retained code change, whatever its cause, is a new
candidate and re-enters both gates.

Hand the diff to a **reviewer agent** — a fleet agent of its own,
in its own pane — and do not read it yourself, and do not review in
your own window. Package diffs pulled into the orchestrator are exactly
the source this architecture keeps out: by the fourth package your
judgment is swimming in the first three's implementation noise, and
having briefed the round you also want it to succeed — a reviewer that
wrote none of it grades without that bias. Split a review pane off the
package's root pane, write-ahead the pane and the reviewer agent
(`role` `package-reviewer`, `kind` `pane` / `agent`, `cleanup_policy`
`close-aux`), read the new pane id from the JSON, and start it:

```bash
herdr pane split <root-pane-id> --cwd <worktree-path> --no-focus
herdr agent start <slug>-review --kind <kind> --pane <new-pane-id>
```

The reviewer shares the implementer's worktree read-only — the intro's
rule bans two *writers* per checkout, and a reviewer is not one. Its
brief is a file-drop like any other and carries: the package brief's
path, the worktree path, the base sha, and the recorded `candidate_sha`;
the instruction to grade `git diff <base-sha> <candidate_sha>` against
the brief's criteria, with evidence, flagging anything outside the
brief's scope; the requirement to name that exact candidate sha in the
verdict; the requirement to label every finding **blocking** (fails an
acceptance criterion, breaks correctness or security, or endangers the
merge) or **non-blocking** (everything else) — a rejecting verdict
needs at least one blocking finding, and non-blocking findings alone
never fail the gate; the
statement that the review is read-only — a reviewer that
"fixes" what it grades smuggles unreviewed edits into the merge; the
no-build rule from the implementer's brief — grading is reading, and a
reviewer that runs the suite fights the serial quick checks (step 8) for
caches and locks; and the output contract — write the verdict to a file
in the round directory and reply with only the path, since pane
scrollback truncates long replies (step 6).

Reviewers and checkers are fleet agents: the same watch loop, wait
block, states, and traps apply, and a settled reviewer means a
verdict file to read, a settled checker a report file. Reviews run no
builds, so any number of reviewers can work while implementers are
still working — the one-heavy-build rule is untouched.

Reviewer kind: pick it from the review's own difficulty and risk, not
as a fixed discount off the implementer's. Foundational, concurrent,
security-sensitive, or data-model packages get a reviewer at least as
strong as their implementer — your strongest kind for the packages you
graded hardest — because a reviewer much weaker than the code it
grades rubber-stamps what it cannot parse. A lower tier fits only
mechanical, well-bounded diffs with explicit acceptance criteria.
Never use the cheapest kind for code review.

You adjudicate. With both gates' results in hand, decide accept, send
back, or drop — that call needs round-level context (merge order,
budgets, how the packages interact) that only you hold. Send the
blocking findings back to the implementing agent as a numbered review
prompt, bundling in any non-blocking ones worth fixing, and wait for
the fix; long feedback is a file-drop (step 5). A blocking finding is
cleared by a fix or by a reviewer verdict — reclassifying it yourself
is how a round quietly ships a rejected package. When a re-grade
surfaces a likely-blocking issue that sat unchanged in the prior
candidate, hand that one finding to a second reviewer of equal or
stronger kind for a focused adjudication.

Every fix invalidates the prior candidate sha: repeat the clean-tree
plumbing, record the new one, and run both gates again — the quick
checks in full, the review as a **re-grade**. Give the reviewer the
prior verdict's path plus the previous and new candidate shas; it
confirms each numbered blocking finding is resolved, reviews
`git diff <prev-candidate> <new-candidate>` for regressions and scope
creep — reading surrounding code where the delta's semantic effects
demand it — and issues a verdict naming the new sha for the complete
candidate. Fall back to a full `base..candidate` grade when history
was rewritten, the fix broadened scope, or the prior verdict cannot be
established.

Budget 2 **correction cycles** per package, counted monotonically: the
initial review is free, and each rejecting verdict — one with blocking
findings — that opens a send-back increments the counter. Quick-check
repairs and non-blocking cleanups re-enter the gates but cost no
cycle. A third rejecting verdict drops the package or goes to the user
to extend the budget; never accept a rejected or stale commit.

After any drop, present the reduced package set and what it no longer
delivers, then get confirmation before merging the remaining packages
(unless the user already authorized unattended continuation after drops).
Closing agent sessions is a package completion criterion. A dropped
package's worktree and branch stay in place for the user to inspect — its
work exists nowhere else — but its implementer, checker and reviewer
sessions close at the drop. An accepted package's sessions close
immediately once both gates have passed and `accepted_sha` is
recorded. Shut each agent and close the checker and reviewer panes
with the shutdown procedure in step 9; the package is not concluded
until all three names are gone from `herdr agent list` and both the
checker and reviewer panes are closed. Merge-target work uses
dedicated agents instead of keeping package sessions alive.

## 8. Quick-check serially

The quick-check gate waits for no verdict: queue it the moment a
candidate sha is recorded. The checks run in the package's worktree
by `<slug>-check`, the checker started there in step 3 — never in
your own window. **Exactly one checker may be `working` at any
moment across the whole round**, package checkers and the merge
checker (step 9) alike: prompt the next one only after the previous
one has settled. That is the one-heavy-build rule, the whole reason
implementers don't build (step 5), and the queue is yours to keep.

The binding stays with you; it is cheap git metadata, not source.
Before prompting and again after the report arrives, require
`git status --porcelain` to be empty and both `git rev-parse HEAD`
and `git rev-parse feat/<slug>` to equal the recorded `candidate_sha`
in the package worktree; this binds the tested tree to the same
commit the reviewer grades.

The check brief is a file-drop (step 5) and carries: the worktree
path and the candidate sha; the package's own quick checks only — it
compiles, its own tests pass — with the commands from the survey
report (step 2), never the repo's full suite, which runs once on the
merge target (step 9), where cross-package failures actually show up;
the rule that a transient infrastructure failure (network, a cache
lock) is a retry on the same candidate, not a new one; no code
changes and no commits; and the output contract — write the result
to `<recorded-round-dir>/<slug>-check-<candidate_sha>.md` with the
exact sha tested, pass or fail, and the verbatim command output, and
reply with only the path.

Accept a report only if it names the recorded candidate sha. A
genuine failure's verbatim output — the report file's path, not your
paraphrase — goes into the combined fix brief of step 7, and any
retained fix, mechanical or otherwise, is a new candidate for both
gates. No changed tree reaches the merge without a matching verdict
and a green check report on its exact sha.

## 9. Merge the round locally

The round ends on a local branch — nothing gets pushed; publishing (push,
PR, merging into the default branch) stays with the user. Once every
non-dropped package has passed review and its quick checks, merge only
those packages. If none remain, skip to step 10.

Create one merge tab for all merge-phase work, bound to the
orchestrator workspace id recorded in step 2 — `--workspace` is
required, because without it `herdr tab create` follows the globally
active workspace and a focus change would place the tab elsewhere.
Write-ahead the tab (`kind` `tab`, `role` `merge-container`) and its
root pane (`kind` `pane`, `role` `container-root-pane`):

```bash
herdr tab create --workspace <orchestrator-workspace-id> --cwd <main-repo-path> --label <round-slug>-merge --no-focus
```

Record the merge tab id and its root pane id. Then split a checker
pane off that root pane, write-ahead the pane and the agent (`role`
`merge-checker`, `kind` `pane` / `agent`, `cleanup_policy`
`close-aux`), and start the **merge checker** `<round-slug>-check`
there with cwd `<main-repo-path>`:

```bash
herdr pane split <merge-root-pane-id> --cwd <main-repo-path> --no-focus
herdr agent start <round-slug>-check --kind <kind> --pane <new-pane-id>
```

Reuse it for every suite run of the merge phase; it is shut with the
shutdown procedure below before the merge tab closes. Every merge
fixer and merge reviewer splits inside this tab too; never use
`--current` here, and never close this tab's root pane — `herdr tab
close` reclaims it.

1. Re-check the main repo: the tree still clean (`git status`) and HEAD
   still on the branch recorded in step 2 (`git rev-parse --abbrev-ref
   HEAD`) — hours may have passed, and uncommitted edits or a mid-round
   branch switch would ride into the merges; surface a mismatch and go
   to step 10 instead of working around it. If the recorded branch itself
   is the merge target, require `git merge-base --is-ancestor <base-sha>
   HEAD`; a failure means the branch was reset or rewritten, so go to
   step 10 instead of merging packages based on stale history. A branch
   that moved forward while retaining the base may still merge — report
   it. Then check out the merge target: if step 2 chose a fresh target,
   write-ahead the branch (`kind` `branch`, `role` `merge-target`,
   `cleanup_policy` `report-only`) and create it now with
   `git switch -c feat/<round-slug> <base-sha>` — an "already exists"
   refusal means the step-2 collision check was dodged, so go to
   step 10 and surface it. Otherwise stay on the recorded branch.
2. Merge the accepted package branches in the agreed order, one at a
   time. Immediately before each merge, require the package worktree to
   be clean and `git rev-parse feat/<slug>` to equal its `accepted_sha`,
   record `pre_merge_sha=$(git rev-parse HEAD)`, then run
   `git merge --no-ff feat/<slug>`. A clean merge is bookkeeping and yours
   to run. A conflicted merge is implementation in the main checkout, not
   the package worktree. Split a fixer pane off the merge tab's root
   pane; write-ahead the pane and the fixer agent (`role` `merge-fixer`,
   `kind` `pane` / `agent`, `cleanup_policy` `close-aux`):

   ```bash
   herdr pane split <merge-root-pane-id> --cwd <main-repo-path> --no-focus
   herdr agent start <slug>-merge --kind <kind> --pane <new-pane-id>
   ```

   Brief that fixer by file-drop to resolve and commit the merge. Do not
   reuse the worktree-rooted implementer: a path written in a brief does
   not change a live agent's cwd, and the conflict index (`MERGE_HEAD`)
   exists only in the main checkout. Exactly one fixer may write the main
   checkout at a time. Once the fixer settles, require a clean committed
   merge, record `candidate_sha=$(git rev-parse HEAD)`, and dispatch
   `<slug>-merge-review` in another pane split the same way off the merge
   tab's root (write-ahead `role` `merge-reviewer`) to grade
   `git diff <pre_merge_sha> <candidate_sha>` read-only, concentrating
   on the conflict resolution and combined behavior. Accept only a
   verdict naming that candidate sha. Start the next merge only after
   this review passes and the pair is shut (shutdown procedure below).
3. Prompt `<round-slug>-check` to run the repo's full build and test
   suite on the merge target — the round's heavy build, and the first
   time the packages meet, so cross-package failures land here. Its
   brief is a file-drop and carries: the merge target branch and its
   current sha, the full build and test commands (survey report,
   step 2), no code changes and no commits, and the output contract —
   write the report to
   `<recorded-round-dir>/<round-slug>-suite-<sha>.md` with the sha,
   pass or fail, and the verbatim output, and reply with only the
   path. While it runs, the checker is the one agent working in the
   main checkout: no fixer is live at the same time and you run no
   git there. On failure, record `pre_fix_sha=$(git rev-parse HEAD)`
   and send the report path by file-drop to one dedicated fixer rooted
   in the main checkout (split and write-ahead as in item 2 if
   needed). Once it settles, require a clean tree and a new commit,
   record `candidate_sha=$(git rev-parse HEAD)`, then dispatch
   `<slug>-merge-review` in another merge-tab pane (write-ahead as in
   item 2) to grade the exact `git diff <pre_fix_sha> <candidate_sha>`
   read-only. Accept only a verdict naming that candidate sha and,
   after the pair is shut (shutdown procedure below), prompt the merge
   checker again on the new sha. Handle one fixer/reviewer pair at a
   time. If a fixer is blocked on a user decision, or the failure
   cannot be resolved this round, persist the failing output, leave
   the merge-target red-suite fix state untouched, and go to step 10.

Throughout, the main checkout changes hands whole: exactly one agent
works in it at a time, and while one does, run no git there yourself —
the no-shared-checkout rule from the intro, applied to you.

**Then shut each finished agent down promptly** — once it is no longer
needed, including each merge pair before the next merge or suite
rerun; do not defer closes to the end of the step. An agent left
running after its package is done keeps a live session holding your
repo context and credentials, keeps occupying a subscription seat,
and will act on any stray input that reaches its pane.
Submit the agent's literal exit command with Enter through its pane, for
example `herdr pane run <pane-id> /quit` for Grok or
`herdr pane run <pane-id> /exit` for agents that use `/exit`; use
`herdr agent send-keys <name> ctrl+c` only as an interrupt fallback after
reading the screen. Confirm the name is gone from `herdr agent list`.
Agent exit is not the end state for an auxiliary pane (package checker,
package reviewer, merge fixer, merge reviewer, merge checker): once
required output is persisted, verify an idle shell with
`herdr pane process-info --pane <pane-id>`, confirm
the recorded container root pane id still exists in the same
workspace/tab (check that id, not a pane count), then
`herdr pane close <pane-id>`. Never close a package workspace root pane
or the merge tab's root pane — `herdr worktree remove --workspace <id>`
needs the package workspace alive, and `herdr tab close` reclaims the
merge tab's root. When merge work is finished, close the merge tab:

```bash
herdr tab close <merge-tab-id>
```

That close is the safety net for any auxiliary pane the prompt closes
missed. Everything the round produced now lives on the merge target;
anything needed after cleanup is a fresh agent's job there.

## 10. Clean up and report

Run this step when merge work finishes, when this round stops after
the round directory exists, and when a later invocation finds a
leftover round directory (steps 2–3), and consume that manifest. A
leftover from another invocation needs the user's decision before
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
   passes, the package agent, its checker and its reviewer are gone,
   and every auxiliary pane is already closed. Leave the container
   root pane in place. Enumerate the workspace's remaining panes (the
   recorded root pane included) and confirm via
   `herdr pane process-info --pane <pane-id>` that each holds only an
   idle shell — herdr shuts down the workspace's
   terminal runtimes before a forced removal, so a vanished agent
   does not make `--force` safe. Fail closed on any non-shell occupant,
   user takeover, or unidentifiable state; retain and report. Only
   then `herdr worktree remove --workspace <id> --force`. A dirty or
   unmerged worktree stays in place for inspection. A dropped
   package's worktree — its commits exist nowhere else — never gets
   force-removed; surface it instead. After a successful remove,
   `rmdir` the exact expected empty parent directory (non-recursive)
   and retain on failure. Do not `git worktree prune`; at most
   `git worktree prune --dry-run --verbose` and report the findings.
2. Delete the merged package branches — worktrees first, branches
   second: git refuses to delete a branch that is still checked out in
   a worktree. Every merged tip is reachable from the target, so
   `git branch -d` succeeds; read a refusal precisely — `used by
   worktree` means step 1 left the worktree behind and says nothing
   about merge state, while `not fully merged` is evidence the package
   never actually merged. Either way investigate; `-D` answers neither.
3. Account for the rest of this round's residue from the manifest —
   round directory, package branches, any merge-target branch this
   round created, the merge tab and its root pane, and worktree parent
   directories. Leave the merge target in place; it is the round's
   output. Append a `state` event per disposition for every resource
   except the round directory, while the manifest still exists.
4. Final report: the merge target branch, then per package — branch,
   correction cycles used, quick-check evidence — plus anything
   dropped. Build every item except the round directory from the
   still-live manifest as one of `removed`, `retained(<reason>)`,
   or `cleanup_failed(<error>)`. Then delete the round directory last,
   using only the exact absolute path recorded on its `created`
   event: `rm -rf "${recorded_round_dir:?}"`, after confirming that
   path still matches the recorded id and that
   `<recorded_round_dir>/manifest.jsonl` carries the `round_id` of
   the round being reclaimed. Do not reconstruct the path from
   `$TMPDIR` and the slug. The `:?` guard keeps an unset recorded
   path from aiming the delete at `/`. It names repo internals and
   has served its purpose. Observe that outcome and fold it into the
   report; there is no post-delete append. What happens to the target
   branch next is the user's call.

Round invariants: implementation — conflict resolution included — belongs
to the agents and diff-grading to the reviewers; builds, tests and
worktree preparation run in checker agents, and codebase surveys in a
survey agent, never in the orchestrator's window; review, quick
checks, and merge bind to the same exact clean commit; a blocking
finding is cleared by a fix or a reviewer verdict, never by
orchestrator reclassification, and correction counters only go up;
exactly one heavy build runs at a time; the round ends on a local
branch and publishing stays with the user; a worktree holding dirty
or unmerged work stays in place; a finished agent session closes
before its package or merge task is considered done; a container root
pane is never closed explicitly (step 9); resources except the round
directory are write-ahead (step 3) and only manifest-confirmed ones
are reclaimed.
