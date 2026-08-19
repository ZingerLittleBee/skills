---
name: herdr-fleet
description: "Run one round of parallel implementation across multiple CLI coding agents (claude, codex, droid, grok, …) in herdr-managed git worktrees, one package per worktree, merged back into one local branch. Invoke with /herdr-fleet <tasks or backlog description>."
disable-model-invocation: true
---

# herdr-fleet

Complete several work packages in parallel by giving each one a
git worktree and a dedicated CLI coding agent inside herdr. You are the
**orchestrator**: you slice the work, brief the agents, watch their state,
dispatch reviewers, and run validation. You never implement, and you never
pull package diffs into your own window — source lives in the agents'
worktrees and gets graded by reviewer subagents (step 7). That split is
what makes the round safe: your judgment on package N stays sharp after
babysitting packages A through M, and no two writers ever share a checkout.

## 1. Preconditions

- Confirm you are inside a herdr-managed pane: `test "${HERDR_ENV:-}" = 1`.
  If not, say so and stop — do not drive herdr from outside herdr.
- The main repo's working tree must be clean (`git status`); surface a dirty
  tree instead of working around it.
- Check `herdr integration status`: every agent kind you plan to assign
  needs its integration to read `current` — the watch loop's state
  detection comes from that integration, so run
  `herdr integration install <kind>` for any kind reading `not installed`
  or `outdated`. (`herdr agent` lists the *supported* kinds only; whether
  an agent binary is actually installed herdr cannot tell — ask the user
  which subscriptions to use if they haven't said.)
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
`feat/<slug>`, worktree label, agent, brief file — so `herdr agent list`
reads as a status board; the round-slug names the brief directory
(step 5) and, when the round needs a fresh merge target, that branch
(below). Agent names are server-global and branches already live in the
repo: check `herdr agent list` and `git branch --list "feat/*"` for
collisions now — the round-slug branch included — and pick a different
slug rather than debug ambiguous targets mid-round.

Now fix the round's **base** and **merge target** from the main repo's
current branch:

- Record the main repo's absolute path (`git rev-parse
  --show-toplevel`), the current branch (`git rev-parse --abbrev-ref
  HEAD`), and its head sha (`git rev-parse HEAD`). The sha is the
  round's base — every worktree gets pinned to it (step 3) — and the
  path is what worktree creation (step 3) and conflict briefs (step 9)
  reference; your shell's cwd hours from now is not a substitute.
- If the current branch is shared and long-lived (the default branch,
  `develop`, `release/*`), or HEAD is detached (`--abbrev-ref` prints
  the literal `HEAD`), the round must not land on it directly: the
  merge target is a new local branch `feat/<round-slug>` created from
  the base sha at merge time (step 9). Otherwise the current branch
  itself is the merge target. Borderline cases are your judgment call.

Present the plan — packages, branch names, merge order, merge target,
agent kind per package — as a short table and get one confirmation
before creating anything (skip only if the user already said to run
unattended).

## 3. One worktree per package

```bash
herdr worktree create --cwd <main-repo-path> --branch feat/<slug> --base <sha> --label <slug> --no-focus
```

Pin every package to the same `--base` commit (the round's base sha from
step 2): it keeps packages from drifting apart if the branch moves
mid-round, and every later verification diffs against it.

Record the workspace id, root pane id, and worktree path from the
JSON — the reviewers (step 7) and validation (step 8) both need the
path. Then make the worktree actually buildable before starting an
agent in it:

- **Binary artifacts don't follow.** Git worktrees share history, not
  ignored build artifacts. If the build depends on a large local artifact
  (a prebuilt xcframework, a vendored binary), copy the real directory into
  the worktree — symlinks often defeat build systems that resolve artifact
  identity through the path.
- Run the project's dependency resolution step in the worktree once
  (e.g. `swift package resolve`, `pnpm install`); retry on transient
  network failures rather than concluding the worktree is broken.
  Resolution contends for the same shared caches as builds, so prepare
  worktrees one at a time.

## 4. Assign agents by difficulty

Map difficulty to the user's subscriptions, strongest kind to the hardest
package. Foundational or architecturally risky packages get the strongest
agent — a weak foundation costs every reviewer and every later round.
Mechanical, well-bounded packages (apply an established pattern, styling
sweeps, copy changes) go to the cheaper kinds. When unsure, assign up.

```bash
herdr agent start <slug> --kind <kind> --pane <root-pane-id>
```

## 5. Brief each agent

A real brief is too long to push through a terminal. Write it as a
Markdown file, one per package, in the round's temp directory: resolve
`$TMPDIR/herdr-fleet-<round-slug>` to an absolute path once, `mkdir -p`
it, and reuse the resolved path all round, prompts included (the
round-slug directory keeps two rounds on one machine out of each
other's briefs; one brief per package at `<dir>/<slug>.md`). Make the
prompt a one-liner pointing at it:

```bash
herdr agent prompt <slug> "Read $TMPDIR/herdr-fleet-<round-slug>/<slug>.md and complete the package it describes."
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
  orchestrator validates serially afterwards. Explain why in the brief:
  concurrent builds across worktrees fight over shared caches and locks and
  make the machine unusable, so a parallel round only works if exactly one
  build runs at a time.
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
for a in <unsettled slugs>; do herdr agent wait "$a" --timeout 540000 & done
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

Keep a per-package status board — agent state, last state change, review
rounds used, next action — and update it on every wake. When an agent
changes state, read its recent output before deciding anything:

```bash
herdr agent read <name> --source recent-unwrapped --lines 120
```

Priorities inside the loop: answer `blocked` agents first (each is stalled
wall-clock), then review settled ones (step 7), then check long-`working`
ones — an agent whose output hasn't changed across several sweeps may be
stuck on an unrecognized prompt or spinning; read the pane and decide.
Surface progress to the user at transitions that matter (package settled,
review sent, validation passed, merge landed), not on every wake.

Known traps and how to handle them:

- **Swallowed first prompt.** Some agents (droid, notably) eat a prompt sent
  during their startup/welcome screen. If an agent is `idle` shortly after
  start with no meaningful output, re-send the pointer prompt — the brief
  file is still on disk, which is one reason it is a file.
- **`blocked`** means the agent is showing an approval or question UI. Read
  the screen before acting; answer with `herdr agent prompt` for free-text
  questions or `herdr agent send-keys <name> <key>` for menu-style prompts.
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

## 7. Review each package — with a reviewer subagent

When an agent settles, first check the plumbing yourself; this is cheap
metadata, not source. `git log <base-sha>..HEAD` in the worktree is the
complete set of commits the package produced — taken from git, never from
the agent's summary — and uncommitted leftovers in `git status` mean the
brief wasn't followed even if the summary reads well. An empty range
means the package produced nothing: re-brief or drop it — an empty
branch has nothing to merge and never reaches step 9.

Then spawn a **reviewer subagent** to grade the diff — do not read it
yourself. Package diffs pulled into the orchestrator window are exactly
the source this architecture keeps out: by the fourth package your
judgment is swimming in the first three's implementation noise, and having
briefed the round you also want it to succeed — a reviewer that wrote none
of it grades without that bias. The reviewer needs only three inputs: the
brief file path, the worktree path, and the base sha. It reads
`git diff <base-sha>..HEAD`, returns a per-criterion verdict with
evidence, and flags anything outside the brief's scope. State in the
reviewer's brief that it is read-only — a reviewer that "fixes" what it
grades smuggles unreviewed edits into the merge. Read-only is also what
lets several reviews run in parallel while other agents are still
working.

Reviewer model: one tier below the session model by default — strong
enough to genuinely parse the diff, cheap enough to run every round.
Escalate to the session model for the packages you graded hardest: a
reviewer much weaker than the code it grades rubber-stamps what it cannot
parse. Never use the cheapest tier for code review.

You adjudicate. With the verdicts in hand, decide accept, send back, or
drop — that call needs round-level context (merge order, review budgets,
how the packages interact) that only you hold. Send findings back to the
implementing agent as a numbered review prompt and wait for the fix; long
feedback is a file-drop (step 5). Budget 2 review rounds per package,
then either accept with documented caveats or drop the package from the
round and say why, stating what the round now lacks. A dropped
package's worktree and branch stay in place for the user to inspect —
its work exists nowhere else — but its agent gets shut down at the
moment of the drop (the drill in step 9), not held for that step's
green-suite gate.

## 8. Validate serially

Only after a package passes review, validate it **in its worktree, one
worktree at a time** — exactly one heavy build runs at any moment. Run
only the package's own quick checks (it compiles, its own tests pass) —
the repo's full suite runs once on the merge target (step 9), where
cross-package failures actually show up. On failure, send the owning
agent the verbatim failing output (not your paraphrase) and re-validate
after the fix; long output is a file-drop (step 5).

## 9. Merge the round locally

The round ends on a local branch — nothing gets pushed; publishing (push,
PR, merging into the default branch) stays with the user. Once every
package has passed review and its quick checks:

1. Re-check the main repo: the tree still clean (`git status`) and HEAD
   still on the branch recorded in step 2 (`git rev-parse --abbrev-ref
   HEAD`) — hours may have passed, and uncommitted edits or a mid-round
   branch switch would ride into the merges; surface a mismatch instead
   of working around it. (A recorded branch that merely moved past the
   base sha still merges — report it.) Then check out the merge target:
   if step 2 chose a fresh target, create it now with
   `git switch -c feat/<round-slug> <base-sha>` — an "already exists"
   refusal means the step-2 collision check was dodged, so stop and
   surface it. Otherwise stay on the recorded branch.
2. Merge the package branches into it in the agreed order, one at a time:
   `git merge --no-ff feat/<slug>`. A clean merge is bookkeeping and
   yours to run; a conflicted merge is implementation and belongs to the
   agent owning the incoming package — brief it (file-drop) to resolve
   and commit the merge, and put the main repo's absolute path (step 2)
   in the brief: the conflict lives in that checkout's index
   (`MERGE_HEAD`), not in the agent's own worktree, and an agent left
   pointed at its worktree will report a clean tree or "resolve" the
   wrong repo. Start the next merge only after the previous one is
   committed.
3. Run the repo's full build and test suite on the merge target — the
   round's heavy build, and the first time the packages meet, so
   cross-package failures land here. Send each failure verbatim to the
   agent whose package owns it and have it fix on the merge target;
   re-run until green.

Throughout, the main checkout changes hands whole: exactly one agent
works in it at a time, and while one does, run no git there yourself —
the no-shared-checkout rule from the intro, applied to you.

**Then shut each finished agent down promptly** — once the merged suite
is green. An agent left running after its package is done keeps a live
session holding your repo context and credentials, keeps occupying a
subscription seat, and will act on any stray input that reaches its pane.
Ask it to quit with its own exit command
(`/exit`, `/quit`, or ctrl+c / ctrl+d via `herdr agent send-keys`), then
confirm the name is gone from `herdr agent list` and the pane is back at a
shell prompt. Everything the round produced now lives on the merge
target; anything needed after cleanup is a fresh agent's job there.

## 10. Clean up and report

The green suite on the merge target gates the cleanup: on failure, keep
every worktree, branch, and pane in place as recovery context for the
fix, and bring the failing output to the user. Once green:

1. Remove each merged package's worktree:
   `herdr worktree remove --workspace <id> --force`. A dropped package's
   worktree — its commits exist nowhere else — never gets
   force-removed; surface it instead.
2. Delete the merged package branches — worktrees first, branches
   second: git refuses to delete a branch that is still checked out in
   a worktree. Every merged tip is reachable from the target, so
   `git branch -d` succeeds; read a refusal precisely — `used by
   worktree` means step 1 left the worktree behind and says nothing
   about merge state, while `not fully merged` is evidence the package
   never actually merged. Either way investigate; `-D` answers neither.
3. Delete the round's brief directory:
   `rm -rf "${TMPDIR:?}/herdr-fleet-<round-slug>"` — the `:?` guard
   keeps an unset `TMPDIR` from aiming the delete at `/`. It names repo
   internals and has served its purpose.
4. Final report: the merge target branch, then per package — branch,
   review rounds used, validation evidence — plus anything dropped or
   left over. What happens to the target branch next is the user's call.

Round invariants: implementation — conflict resolution included — belongs
to the agents and diff-grading to the reviewers; exactly one heavy build
runs at a time; the round ends on a local branch and publishing stays
with the user; a worktree holding unmerged work stays in place; a
finished agent gets shut down.
