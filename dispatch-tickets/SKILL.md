---
name: dispatch-tickets
description: "Run a set of tracker tickets to completion in one session: the main agent is a dispatcher that never implements. It contracts the dependency graph's straight chains and layers the result into waves; a wave of two or more chains runs in parallel as one herdr-fleet round, one package per chain, when herdr is available, and everything else runs serially through fresh implementer subagents. Each result is verified and tickets are closed wave by wave. Invoke with /dispatch-tickets #N #N … or /dispatch-tickets parent=#N [branch=…] [mode=serial]."
disable-model-invocation: true
---

# dispatch-tickets

Complete a set of tickets in a single session. You are the **dispatcher**:
you order the work into chains and waves, choose how each wave runs, brief
the implementers, verify their output, and close tickets. Your own hands
touch only the tracker, git plumbing, and test commands. Implementation,
including reading source, happens exclusively in other agents' windows.
That division is the whole reason this architecture works: every ticket
gets an implementer with a fresh context window, so ticket N's
implementation noise can never contaminate ticket N+1, and a dispatcher
window kept free of source code stays sharp on the last ticket too.

A wave runs one of two ways:

- **Serial path** (section 6): one fresh subagent per ticket, one after
  another, on the run's branch in the main checkout.
- **Fleet path** (section 7): one round of the sibling `herdr-fleet`
  skill, one package per chain, all chains in parallel, merged back onto
  the run's branch.

## 1. Preconditions

- Working tree must be clean (`git status`); a dirty tree makes verification
  and commit attribution impossible. Stop and surface it.
- This is a long, hands-off run in which agents edit files and run
  commands continuously. If the session is not in an auto-accepting permission
  mode, tell the user each approval prompt will stall the run, and let them
  restart in a suitable mode before you begin.
- The host must be able to spawn a subagent with its own context window
  and wait for its result: the serial path, the verifiers and the final
  sweep all run on it. If the host has no such facility, stop and say
  so; the dispatcher never implements a ticket itself.
- If the repo declares its tracker conventions (e.g. `docs/agents/issue-tracker.md`),
  follow those. Default: GitHub issues via the `gh` CLI.
- **Fleet availability**, checked once: the fleet path is available when
  `herdr status server` reports `status: running` and the herdr-fleet
  skill file is found. The fleet skill is user-invoked, so you reach it
  by reading that file, never by invoking it as a skill. Look for it in
  this order and record the first path that exists as the **fleet
  skill path**: `../herdr-fleet/SKILL.md` relative to this skill's base
  directory (when the host names one), then
  `<repo>/.claude/skills/herdr-fleet/SKILL.md`,
  `~/.agents/skills/herdr-fleet/SKILL.md` and
  `~/.claude/skills/herdr-fleet/SKILL.md`. When herdr is running but no
  path exists, tell the user the fleet is unavailable for that reason
  and the whole run goes serial; the plan table (section 5) repeats it.
  An explicit `mode=serial` argument makes the fleet unavailable for the
  run.

## 2. Gather the tickets

Accept either an explicit ticket list (`#319 #320 …`) or `parent=#N`, in which
case discover the children: native sub-issues first
(`gh api --paginate repos/<owner>/<repo>/issues/<N>/sub_issues`), otherwise
issues whose body references the parent. Then split by state: the run's set
is the open tickets only. A closed child, or a closed ticket in an explicit
list, is already done: it is never dispatched again, it counts as a
satisfied blocker, and the plan table (section 5) lists it as skipped. This
is what lets a half-finished parent be run again.

Read every ticket in the set in full (`gh issue view <n> --comments`), and
the parent spec if there is one: you need each ticket's acceptance criteria
to verify later, and the parent for tie-breaking questions.

Build the dependency graph from the tracker's native blocking relations.
On GitHub, list each ticket's blockers with
`gh api --paginate repos/<owner>/<repo>/issues/<n>/dependencies/blocked_by`,
which returns the blocking issues with their repository, number and state;
`issue_dependencies_summary` on the issue only counts them and names none. A
failed read is not an empty list: stop and surface it. Only when a ticket
has no native blockers, read its body: a `Blocked by:` line, or a
`## Blocked by` section whose list items reference the blockers, where
"None" means no blockers. Only edges between tickets of the set count; a
closed blocker is already satisfied. Never trust the order the arguments
were written in; the graph is the truth. If the graph has a cycle, or a
ticket is blocked by an open issue outside the set (another repository's
included), stop and ask.

## 3. Contract chains, then layer into waves

**Integration groups** come first. to-tickets allows one exception to
per-ticket green: a wide refactor whose migrate batches cannot stay green
alone lets them share an integration branch, and all of them block a final
integrate-and-verify ticket, the only one that promises green. Recognize a
group from ticket text: the verify ticket (**V**) says it is the
integrate-and-verify step, and the group's **batches** are the tickets
blocking V that say they cannot stay green alone.

The group's **members** are the batches, V, and every ticket on a
dependency path from a batch to V (a contract ticket between the batches
and V, say). That closure is what makes collapsing safe: with a ticket
left outside while it sits between two members, the collapsed node would
both block it and depend on it. Text is the only evidence, so the plan
table lists every group with its members and the one confirmation is
where a misread group gets caught.

Collapse each group into one node before contracting chains, then check
the collapsed graph for a cycle once more; one means the group was
misread, so stop and ask. The node's blockers are the members' blockers
outside the group; its dependents are the tickets outside the group that
any member blocks. The node is a chain in its own right, run in sequence
as to-tickets asks: the members in graph order (any order where the
graph sets none), V last. Three rules set it apart:

- Every member but V is **red-tolerant**, since the group promises green
  only at V: it skips every test run and quick check, and its
  verification checks only that its own work is complete against its
  criteria. V gets full verification, and its fixes may touch any
  member's code, since integrating is its job.
- The group lives on its own **integration branch** and reaches the run's
  branch only once V is green, so no other chain and no later wave ever
  builds on a red tree.
- All the group's tickets close together once V is green; if V never gets
  there, none of them close.

A **chain** is a straight run of tickets with no fork and no join inside
it. Contract the graph edge by edge: merge A→B into one chain when B is
A's only dependent and A is B's only blocker, and repeat until no edge
qualifies. Every ticket ends up in exactly one chain, ordered by its
edges; a ticket with no qualifying edge is a chain of one. A chain can
only run in order anyway, so giving it to one package loses nothing,
while each fork and each join stays a boundary between chains.

A chain's **wave** is the length of the longest path of chains leading
to it: chains with no blockers are wave 1, and a chain whose deepest
blocking chain sits in wave k is wave k+1. The chains of one wave are
independent of each other. Waves run strictly in order, and a wave starts
only once the previous one has **concluded**: on the serial path, every
ticket verified (section 6) and closed; on the fleet path, every package
merged on the branch, the round's suite green, and the tickets closed
(section 7).

Choose each wave's path:

- **Fleet path** when the fleet is available (section 1) and the wave
  holds two or more chains. Parallel wall-clock is its only payoff; a
  round's fixed overhead (scouts, worktree preparation, a reviewer per
  package, a merge and a full suite) is worth paying only when chains
  genuinely run side by side.
- **Serial path** otherwise: every single-chain wave, and every wave when
  the fleet is unavailable. On the serial path a chain runs ticket by
  ticket in its order.

## 4. Branch

An explicit `branch=` argument wins. Otherwise derive `feat/<slug>` from the
parent issue title (or the common theme of the tickets), reuse it if it
exists, and create it from the default branch if not. The run's branch
is always a feature branch: if `branch=` names the default branch,
`develop`, `release/*` or any other shared long-lived branch, stop and
ask for another name. Check it out in the main checkout. All tickets
land on this one branch, on both paths: serial tickets commit to it
directly (an integration group through its integration branch, section
6), and a fleet round takes it as its merge target. The user merges it
however they like afterwards.

## 5. Grade the tickets and present the plan

Grade every ticket from its text, before any wave starts:

- **Mechanical**: crisp boundaries, an established pattern. Prefactors,
  deletion/cleanup sweeps, applying a known pattern to more call sites,
  i18n/config chores.
- **Foundational**: anything later tickets build on (skeletons, new
  architecture), anything stateful or lifecycle-heavy, anything the
  parent spec flags as risky.
- **Ordinary**: everything else.

Foundations fail expensively (every later ticket inherits their flaws), so
when unsure, grade up. The grade picks the model on either path:

- Serial path: when the host lets you choose a subagent's model,
  mechanical tickets run on a cheaper one and ordinary and foundational
  tickets inherit the session model.
- Fleet path: a package takes the highest grade among its chain's
  tickets. Mechanical maps to the `smol` slot, ordinary to `default`,
  foundational to `slow`, and a chain whose tickets are all UI tickets
  goes to `ui` as herdr-fleet step 5 defines; a chain mixing UI and
  other work stays on the slot its grade maps to. `hard` is only for a
  chain the user names.

If any wave takes the fleet path, run herdr-fleet sections 1 and 2 now
(slot file, preconditions, slot resolution and any integration install
question), so the plan can name each slot's active pair.

Then present the whole run as a short table and get one confirmation
before dispatching (skip the pause only if the user already told you to
run unattended): waves in order, the chains in each with their tickets in
order, each integration group with its members and V, any integration
branch left over from an earlier run (section 6) with the choice to
resume on it or start fresh, path per wave (with the reason when the
fleet is unavailable), per ticket its grade, per serial ticket its model
and per fleet package its slot and active pair, the closed tickets
skipped, and the branch. This is the last cheap
moment to catch a wrong plan, and this single confirmation is the
authority for every wave and every fleet round of the run.

## 6. The serial path

Run the wave's chains one at a time, each ticket by ticket in chain
order, all on the branch in the main checkout. For each ticket, first
record the baseline: `git rev-parse HEAD`. Everything the ticket produced
is `git log <baseline>..HEAD`: commit hashes for the close comment, and
the diff for verification, taken from git, not from the subagent's
self-report.

Then spawn a fresh subagent with the host's subagent facility and wait
for its result before anything else (the next ticket builds on it). Its
brief, filled in:

```
Complete <tracker> ticket #<N>: read it first with `gh issue view <N> --comments`,
and read the parent spec #<P> for context. Work on branch <branch> in <repo-path>.
Follow TDD discipline: failing test first, then implementation, in small
red-green slices. Follow the repo's conventions (CLAUDE.md / AGENTS.md), domain
glossary (CONTEXT.md), and ADRs. Run the tests you added or changed plus any
affected E2E; when green, commit with Conventional Commits (multiple commits
are fine), each commit body carrying the line `Refs: #<N>`. Return: a summary
of changes (files + line refs), the exact test commands you ran with their
results, and the commit hashes. If the ticket's assumptions contradict what
you find in the code (an earlier ticket changed the ground under it, or the
work turns out to be already done), do not improvise around the conflict:
stop and return a report starting with "BLOCKED:" describing the
contradiction. Do NOT push. Do NOT close the issue: the dispatcher closes it
after verification.
```

A "BLOCKED:" return is not a failure: it means the ticket is stale. Stop
the run and surface the contradiction to the user; re-briefing an
implementer to guess its way around a wrong ticket produces confident
garbage.

When the subagent returns, **verify yourself, never trust the report**:

1. `git log <baseline>..HEAD` shows new commits, and `git status` is clean
   again. Uncommitted leftovers mean the brief wasn't followed, which is a
   failure even if tests pass.
2. Re-run the test commands the subagent reported; they must actually pass.
3. Dispatch a **verifier** subagent (a cheaper model where the host lets
   you choose) carrying the ticket's acceptance criteria and the baseline
   sha; it reads `git diff <baseline>..HEAD` and returns a per-criterion
   verdict with evidence. Reading the diff yourself would pull into your
   window exactly the source code this architecture exists to keep out,
   and the verifier, having written none of the code, grades it without
   the implementer's bias.

An implementer has every incentive to report success; re-running its commands
and grading its diff independently cost minutes, and they are what stand
between one bad ticket and five subsequent tickets built on it.

On failure: dispatch a fix-up subagent carrying the verbatim failure output
and the original brief, **escalated to the session model** if the first
attempt ran on a cheaper one; retrying a reasoning failure on the same
model mostly replays it. Budget: 2 fix-ups per ticket. If it still fails,
**stop the entire run** (never continue to later tickets on a broken
foundation), leave the branch as-is, and report exactly where and why it
stopped.

On success: close the ticket with a comment listing the commit hashes, then
move to the next.

**An integration group on the serial path.** Record the group base
(`git rev-parse HEAD` on the run's branch), then create and check out its
integration branch from that sha. Its name is `<branch>-int-<V>`; when a
branch by that name is left over from an earlier run, the plan table
(section 5) lists it with its commits, and the new attempt takes the
first free `<branch>-int-<V>-<k>` and leaves the old branch untouched,
unless the user chose at confirmation to resume on it.

Resuming checks out the old branch as is and takes
`git merge-base <branch> <old-integration-branch>` as the group base
instead of the run's HEAD. A red-tolerant member whose `Refs:` commits
are already on it (`git log --grep='^Refs: #<N>$' <group-base>..HEAD`)
starts at verification, not at an implementer. That verification needs
no new commit: a clean tree, and a verifier grading exactly those
commits against the member's criteria. Only a gap the verifier names
dispatches an implementer, briefed that those commits are its own
earlier work and that it completes what is missing.

Run the group's tickets in order with the loop above, changed in three
places:

- A red-tolerant member's brief replaces the testing sentences with:
  this ticket belongs to an integration group whose tree may stay red
  until #<V>; complete this ticket's work, run no tests, and commit.
- A red-tolerant member's verification is step 1 plus a verifier that
  checks its work is complete against its criteria; step 2 is skipped,
  and nothing closes yet.
- V runs with the full brief. Its verification replaces steps 1 to 3:
  V may add no commits when the members already integrate cleanly, so
  the conditions are a clean tree, a verifier grading
  `git diff <group-base>..HEAD` against every member's criteria and V's,
  and a subagent running the repo's full check suite on the integration
  branch's HEAD. A failure gets V's fix-up budget, and those fix-ups may
  touch any member's code.

Once V passes, check out the run's branch, `git merge --no-ff` the
integration branch, delete it with `git branch -d`, and close every group
ticket, each with its own commits:
`git log --oneline --grep='^Refs: #<N>$' <group-base>..HEAD`. V's close
comment names the verified integration head and the suite result, since
it may have no commits of its own. If V stays red, the run stops as for
any failed ticket: nothing in the group closes, the integration branch
stays for inspection, and the main checkout goes back to the run's
branch.

## 7. The fleet path

Read the fleet skill path (section 1) in full and run one herdr-fleet
round per fleet wave, its sections 3 through 10, as its orchestrator.
Everything in herdr-fleet that this section does not override holds as
written, including its turn, shell and context disciplines and its
one-heavy-build rule.

**Round setup** (herdr-fleet step 3):

- Round-slug: the branch slug plus `-w<k>`, within the 19-character
  limit. Package slug: `t<first-ticket>-<short>`, same limit.
- Record the wave's base: the branch HEAD at round start. The branch is
  checked out in the main checkout and is not shared or long-lived, so
  herdr-fleet's rule makes it the round's merge target directly.
- Each chain in the wave is exactly one package, holding its tickets in
  chain order: the packaging is fixed by section 3, and the round never
  splits a ticket, moves one to another package, or merges chains. The
  step's slicing work shrinks to what the chains leave open: scouts still
  report per package the files it will touch, its overlap with the
  wave's other packages, and the convention files and specs to read, and
  they settle the merge order for overlapping packages. Quick checks are
  per package and come from each round's scouts: the package's final
  quick check, and for every hand-off point inside its chain a **prefix
  check** covering only the tickets finished by then (a test a later
  ticket adds does not exist yet at that point). Only the per-repo
  commands (dependency resolution, build, full suite) carry forward from
  the first fleet round's scout report instead of being re-surveyed, and
  only while no ticket has changed the files that define them. Add one
  question to that per-repo report: whether a single test file runs
  without a heavy build (a vitest or pytest file does; a cargo or
  xcodebuild target does not).
- An integration group (section 3) is one package like any chain, and
  its package branch is the group's integration branch: the gates and
  the merge already keep it off the run's branch until V is green.
- A scout may raise a package's grade and slot, never lower it; raising
  to `hard` needs the user. A scout report that contradicts a ticket
  (the work is already done, the ground it assumes is gone) is a stale
  ticket, handled as a `BLOCKED:` question below.
- The plan confirmation is the one from section 5: present the round's
  plan table for the record and continue. Worktree decisions for
  leftovers from an earlier round still belong to the user, as
  herdr-fleet step 3 says.

**Package brief** (herdr-fleet step 5), in addition to what that step
requires:

- Every ticket of the chain, in order, with its full body and comments,
  and the parent spec, fetched by you and written as files in the round
  directory, secrets redacted. Implementers may run another vendor's CLI
  with no tracker login and no skills, so the brief carries everything
  they read.
- The rule that each prompt names **one current ticket**: the agent
  completes that ticket only, commits it with the line `Refs: #<N>` in
  every commit body, and ends its turn with the summary contract. A
  commit fixing a review finding carries the `Refs:` line of the ticket
  the finding names instead.
- TDD discipline written out: failing test first, then implementation,
  in small red-green slices. The implementer still runs no heavy build
  or suite. When the scout report says a single test file runs without
  a heavy build, the brief allows running exactly the test files the
  ticket adds or changes, so each red-green step stays observable;
  otherwise the quick check (herdr-fleet step 8) is the first run of
  those tests.
- The stale-ticket rule: if the ticket's assumptions contradict the
  code, the implementer stops and ends its turn with a `QUESTION`
  summary whose question begins `BLOCKED:` and describes the
  contradiction.
- For an integration group: every member but V is red-tolerant
  (section 3), so its agent completes its ticket's work, runs no tests
  and commits; V's agent integrates, may touch any member's code, may
  finish without a commit when nothing needs changing, and gets the full
  TDD rules above.
- The issues stay open: the dispatcher closes them.

**One fresh implementer per ticket.** A chain is several tickets in one
worktree, and one agent carrying all of them would fill its context the
way this skill exists to prevent. The first prompt names the chain's
first ticket. When the implementer settles with `DONE` on a ticket that
is not the chain's last:

1. Check the plumbing on that ticket alone:
   `git -C <worktree-path> status --porcelain` empty and new commits
   since the previous ticket's head, each carrying its `Refs:` line.
2. Queue the prefix check for this hand-off point on the ticket's head,
   exactly as herdr-fleet step 8 runs a quick check for a candidate
   (same check pane, same serial queue, same sha binding). Later tickets
   build on this one, so its tests must be green before they start. A
   `FAIL` goes through triage as in step 8, and a genuine one goes back
   to the same live agent for that ticket; that repair costs no
   correction cycle. A red-tolerant member skips this step: record its
   check as skipped, never as passed.
3. Hand off once the ticket is cleared: a prefix check `PASS` bound to
   its head, or, for a red-tolerant member, step 1 alone. Exit the agent
   exactly as herdr-fleet step 6's slot fallback does (the pane stays)
   and append a `state` event marking it `removed`. Start a fresh
   `<slug>` in the same pane on the package slot's current active pair:
   the same pair unless a slot fallback (herdr-fleet step 6) has moved
   the slot since, and never a pair marked failed. Write it ahead under
   its own resource key
   `package/<slug>/implementer-<n>`, with `<n>` counting the agents the
   package has had. Prompt it with the brief path, the next ticket, the
   next summary path, and the instruction to read
   `git log <wave-base>..HEAD` in its checkout before starting.

Summary paths keep counting across hand-offs (`<slug>-summary-<n>.md`
never restarts at 1), so no agent's summary can be mistaken for an
earlier ticket's. These hand-offs are planned, so they spend none of
herdr-fleet's restart budget. Only the `DONE` on the chain's last ticket
makes the package a candidate for the gates of herdr-fleet steps 7 and
8; the reviewer grades the whole `base..candidate` diff against every
ticket's acceptance criteria and names the ticket in each finding. A
chain may have run on more than one vendor after a fallback, so the
reviewer's vendor differs from every implementer vendor the package
has had. A
send-back goes to the implementer that is live at that point, and each
fix commit carries the `Refs:` line of the ticket its finding names, not
the current ticket's. A package's correction budget is one cycle per
ticket in its chain, never fewer than herdr-fleet's 2.

**Questions during the round.** A `BLOCKED:` question always goes to the
user, never answered from the brief, since only the user can re-scope a
ticket. The rest of the wave keeps running meanwhile. Unless the user's
answer resolves the ticket, that package goes no further: it is dropped
with its worktree retained (its committed tickets exist nowhere else),
and the run stops after this round's step 10.

**Merge phase** (herdr-fleet step 9): a conflict-merge or suite-fix
brief requires every commit to carry a `Refs:` line for each ticket its
change serves, so the tickets' close comments include the fixes that
made them work.

**Concluding the wave.** herdr-fleet's final report (step 10) is an
interim wave report here: it ends no turn. The wave has concluded when
every package merged and the suite passed on the branch's HEAD; record
that HEAD as the wave's **green head**. Then close each ticket with a
comment listing its own commits,
`git log --oneline --grep='^Refs: #<N>$' <wave-base>..<green-head>`,
and naming the branch, and start the next wave in the same turn.

Anything short of that stops the run once the round's step 10 is done: a
dropped package, a merge the round aborted, a red suite, or an unresolved
`BLOCKED:` question. On a green suite, close the tickets of the packages
that did merge; on a red one, close none of the wave's tickets. Later
waves never start on a partial foundation.

## 8. Final sweep and report

After the last wave, dispatch one more subagent (a cheaper model where
the host lets you choose) to run the repo's full check suite: lint,
typecheck, full tests, full E2E, whatever the repo's CI runs. Per-ticket
runs only cover the tests each ticket touched; cross-ticket breakage
surfaces here. Skip the sweep when the last wave was a fleet round whose
suite passed on the branch's current HEAD. A failed sweep follows the
serial path's fix-up rule (session model, same budget); if it stays red,
the final report leads with that.

Then give the final report: the waves, their chains and the path each
wave took, then per ticket: commits, test evidence, retries or correction
cycles used and why, and, for fleet tickets, the model and CLI that
actually did it. Add each fleet round's archive path, and anything left
over (TODOs, warnings, flaky tests observed, retained worktrees).

Red lines for the whole run: never push; never modify or close the parent
spec; never skip or reorder tickets, and never split one ticket or fold
several into one (a chain's tickets share a package, each keeping its own
commits and its own close).
