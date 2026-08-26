---
name: herdr-fleet
description: "Run one round of parallel implementation across multiple CLI coding agents (claude, codex, droid, grok, …) in herdr-managed git worktrees, one package per worktree, merged back into one local branch. Invoke with /herdr-fleet followed by tasks or a backlog description."
disable-model-invocation: true
---

# herdr-fleet

Complete several work packages in parallel by giving each one a
git worktree and a dedicated CLI coding agent inside herdr. You are the
**orchestrator**: you slice the work, brief the agents, watch their state,
dispatch reviewers, and run validation. You never implement, and you
never pull package diffs into your own window — source lives in the
agents' worktrees and gets graded by dedicated reviewer agents in
their own panes (step 7). That split is what makes the round safe:
your judgment on package N stays sharp after babysitting packages A
through M, and no two writers ever share a checkout.

## 1. Preconditions

- Confirm you are inside a herdr-managed pane: `test "${HERDR_ENV:-}" = 1`.
  If not, say so and stop — do not drive herdr from outside herdr.
- The main repo's working tree must be clean (`git status`); surface a dirty
  tree instead of working around it.
- Check `herdr integration status`: every agent kind you plan to
  assign (reviewer kinds included) needs its integration to read
  `current` — the watch loop's state detection comes from that
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
`feat/<slug>`, worktree label, agent, reviewer agent `<slug>-review`,
merge fixer `<slug>-merge`, merge reviewer `<slug>-merge-review`, and
brief file — so `herdr agent list` reads as a status board; the
round-slug names the brief directory (step 5) and, when the round
needs a fresh merge target, that branch (below). Agent names are
server-global and branches already live in the repo: check
`herdr agent list` and `git branch --list "feat/*"` for
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
JSON — the reviewers (step 7) and the quick checks (step 8) both need
the path. Then make the worktree actually buildable before starting an
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
dispatched, a settled reviewer gets its verdict read (step 7) — then check long-`working` ones — an agent whose output
hasn't changed across several sweeps may be stuck on an unrecognized
prompt or spinning; read the pane and decide.
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
package's root pane, read the new pane id from the JSON, and start the
reviewer in it:

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

Reviewers are fleet agents: the same watch loop, wait block, states,
and traps apply, and a settled reviewer means a verdict file to read.
Reviews run no builds, so any number of reviewers can work while
implementers are still working — the one-heavy-build rule is untouched.

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
work exists nowhere else — but its implementer and reviewer sessions close
at the moment of the drop. An accepted package's implementer and reviewer
sessions close immediately once both gates have passed and
`accepted_sha` is recorded. Do not mark the
package concluded until both names are gone from `herdr agent list` and
their panes are back at shell prompts, using the shutdown procedure in
step 9. Merge-target work uses dedicated agents instead of keeping package
sessions alive.

## 8. Quick-check serially

The quick-check gate waits for no verdict: queue it the moment a
candidate sha is recorded, **in the package's worktree, one worktree
at a time** — exactly one heavy build runs at any moment, which is the
whole reason implementers don't build (step 5). Before and after the
checks, require `git status --porcelain` to be empty and both
`git rev-parse HEAD` and `git rev-parse feat/<slug>` to equal the
recorded `candidate_sha`; this binds the tested tree to the same
commit the reviewer grades. Run only the package's own quick checks
(it compiles, its own tests pass) — the repo's full suite runs once on
the merge target (step 9), where cross-package failures actually show
up. A transient infrastructure failure (network, a cache lock) is a
retry on the same candidate, not a new one. A genuine failure's
verbatim output (not your paraphrase) goes into the combined fix brief
of step 7; long output is a file-drop (step 5), and any retained fix,
mechanical or otherwise, is a new candidate for both gates. No changed
tree reaches the merge without a matching verdict and a green quick
check on its exact sha.

## 9. Merge the round locally

The round ends on a local branch — nothing gets pushed; publishing (push,
PR, merging into the default branch) stays with the user. Once every
non-dropped package has passed review and its quick checks, merge only
those packages. If none remain, skip this step and report the dropped
worktrees and branches.

1. Re-check the main repo: the tree still clean (`git status`) and HEAD
   still on the branch recorded in step 2 (`git rev-parse --abbrev-ref
   HEAD`) — hours may have passed, and uncommitted edits or a mid-round
   branch switch would ride into the merges; surface a mismatch instead
   of working around it. If the recorded branch itself is the merge
   target, require `git merge-base --is-ancestor <base-sha> HEAD`; a
   failure means the branch was reset or rewritten, so stop instead of
   merging packages based on stale history. A branch that moved forward
   while retaining the base may still merge — report it. Then check out
   the merge target:
   if step 2 chose a fresh target, create it now with
   `git switch -c feat/<round-slug> <base-sha>` — an "already exists"
   refusal means the step-2 collision check was dodged, so stop and
   surface it. Otherwise stay on the recorded branch.
2. Merge the accepted package branches in the agreed order, one at a
   time. Immediately before each merge, require the package worktree to
   be clean and `git rev-parse feat/<slug>` to equal its `accepted_sha`,
   record `pre_merge_sha=$(git rev-parse HEAD)`, then run
   `git merge --no-ff feat/<slug>`. A clean merge is bookkeeping and yours
   to run. A conflicted merge is implementation in the main checkout, not
   the package worktree. Split a new pane rooted there and start a
   dedicated fixer:

   ```bash
   herdr pane split --current --cwd <main-repo-path> --no-focus
   herdr agent start <slug>-merge --kind <kind> --pane <new-pane-id>
   ```

   Brief that fixer by file-drop to resolve and commit the merge. Do not
   reuse the worktree-rooted implementer: a path written in a brief does
   not change a live agent's cwd, and the conflict index (`MERGE_HEAD`)
   exists only in the main checkout. Exactly one fixer may write the main
   checkout at a time. Once the fixer settles, require a clean committed
   merge, record `candidate_sha=$(git rev-parse HEAD)`, and dispatch
   `<slug>-merge-review` in another main-checkout pane to grade
   `git diff <pre_merge_sha> <candidate_sha>` read-only, concentrating on
   the conflict resolution and combined behavior. Accept only a verdict
   naming that candidate sha, then shut both merge agents down. Start the
   next merge only after this review passes.
3. Run the repo's full build and test suite on the merge target — the
   round's heavy build, and the first time the packages meet, so
   cross-package failures land here. On failure, record
   `pre_fix_sha=$(git rev-parse HEAD)` and send the verbatim output by
   file-drop to one
   dedicated fixer rooted in the main checkout (create it as in step 2
   if needed). Once it settles, require a clean tree and a new commit,
   record `candidate_sha=$(git rev-parse HEAD)`, then dispatch
   `<slug>-merge-review` in another main-checkout pane to grade the exact
   `git diff <pre_fix_sha> <candidate_sha>` read-only.
   Accept only a verdict naming that candidate sha, shut both agents down,
   and re-run the suite. Handle one fixer/reviewer pair at a time until
   the suite passes and `git status --porcelain` is empty.

Throughout, the main checkout changes hands whole: exactly one agent
works in it at a time, and while one does, run no git there yourself —
the no-shared-checkout rule from the intro, applied to you.

**Then shut each finished agent down promptly** — once it is no longer
needed. An agent left running after its package is done keeps a live
session holding your repo context and credentials, keeps occupying a
subscription seat, and will act on any stray input that reaches its pane.
Submit the agent's literal exit command with Enter through its pane, for
example `herdr pane run <pane-id> /quit` for Grok or
`herdr pane run <pane-id> /exit` for agents that use `/exit`; use
`herdr agent send-keys <name> ctrl+c` only as an interrupt fallback after
reading the screen. Confirm the name is gone from `herdr agent list` and
the pane is back at a shell prompt. Everything the round produced now
lives on the merge target; anything needed after cleanup is a fresh
agent's job there.

## 10. Clean up and report

The green suite on the merge target gates the cleanup: on failure, keep
every worktree, branch, and pane in place as recovery context for the
fix, and bring the failing output to the user. Once green:

1. Remove each merged package's worktree:
   first require `git status --porcelain` to be empty, the branch tip to
   equal its recorded `accepted_sha`, and
   `git merge-base --is-ancestor <accepted_sha> <merge-target>` to pass;
   then run `herdr worktree remove --workspace <id> --force`. A dirty or
   unmerged worktree stays in place for inspection. A dropped package's
   worktree — its commits exist nowhere else — never gets force-removed;
   surface it instead.
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
   correction cycles used, quick-check evidence — plus anything dropped
   or left over. What happens to the target branch next is the user's call.

Round invariants: implementation — conflict resolution included — belongs
to the agents and diff-grading to the reviewers; review, quick checks,
and merge bind to the same exact clean commit; a blocking finding is
cleared by a fix or a reviewer verdict, never by orchestrator
reclassification, and correction counters only go up; exactly one heavy
build runs at a time; the round ends on a local branch and publishing stays with the
user; a worktree holding dirty or unmerged work stays in place; a finished
agent session closes before its package or merge task is considered done.
