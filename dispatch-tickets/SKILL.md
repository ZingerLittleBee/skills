---
name: dispatch-tickets
description: "Run a set of tracker tickets to completion in one session: the main agent is a dispatcher that never implements. It layers the dependency graph into waves; a wave of independent tickets runs in parallel as one herdr-fleet round when herdr is available, otherwise tickets run serially through fresh implementer subagents. Each result is verified and tickets are closed wave by wave. Invoke with /dispatch-tickets #N #N … or /dispatch-tickets parent=#N [branch=…] [mode=serial]."
disable-model-invocation: true
---

# dispatch-tickets

Complete a set of tickets in a single session. You are the **dispatcher**:
you order the work into waves, choose how each wave runs, brief the
implementers, verify their output, and close tickets. Your own hands touch
only the tracker, git plumbing, and test commands. Implementation,
including reading source, happens exclusively in other agents' windows.
That division is the whole reason this architecture works: each
implementer starts with a fresh context window, so ticket N's
implementation noise can never contaminate ticket N+1, and a dispatcher
window kept free of source code stays sharp on the last ticket too.

A wave runs one of two ways:

- **Serial path** (section 6): one fresh subagent per ticket, one after
  another, on the run's branch in the main checkout.
- **Fleet path** (section 7): one round of the sibling `herdr-fleet`
  skill, one ticket per worktree, all implementers in parallel, merged
  back onto the run's branch.

## 1. Preconditions

- Working tree must be clean (`git status`); a dirty tree makes verification
  and commit attribution impossible. Stop and surface it.
- This is a long, hands-off run in which agents edit files and run
  commands continuously. If the session is not in an auto-accepting permission
  mode, tell the user each approval prompt will stall the run, and let them
  restart in a suitable mode before you begin.
- If the repo declares its tracker conventions (e.g. `docs/agents/issue-tracker.md`),
  follow those. Default: GitHub issues via the `gh` CLI.
- **Fleet availability**, checked once: the fleet path is available when
  `herdr status server` reports `status: running` and
  `../herdr-fleet/SKILL.md`, relative to this skill's base directory,
  exists. The fleet skill is user-invoked, so you reach it by reading
  that file, never through the Skill tool. An explicit `mode=serial`
  argument makes the fleet unavailable for the run.

## 2. Gather the tickets

Accept either an explicit ticket list (`#319 #320 …`) or `parent=#N`, in which
case discover the children: native sub-issues first, otherwise open issues
whose body references the parent.

Read every ticket in full (`gh issue view <n> --comments`), and the parent
spec if there is one: you need each ticket's acceptance criteria to verify
later, and the parent for tie-breaking questions.

Build the dependency graph from the tracker's native blocking relations
(`issue_dependencies_summary.blocked_by` on GitHub), falling back to
`Blocked by:` lines in ticket bodies. Never trust the order the arguments
were written in; the graph is the truth. If the graph has a cycle, or a
ticket is blocked by an open issue outside the given set, stop and ask.

## 3. Layer the graph into waves

A ticket's **wave** is the length of the longest blocker chain leading
to it: tickets with no blockers in the set are wave 1, and a ticket
whose deepest blocker sits in wave k is wave k+1. Every blocker of a
ticket therefore lands in an earlier wave, and the tickets of one wave
are independent of each other. Waves run strictly in order, and a wave
starts only once the previous one has **concluded**: every ticket merged
on the branch, the checks green, the tickets closed.

Choose each wave's path:

- **Fleet path** when the fleet is available (section 1) and the wave
  holds two or more tickets. Parallel wall-clock is its only payoff;
  a round's fixed overhead (scouts, worktree preparation, a reviewer per
  ticket, a merge and a full suite) is worth paying only when tickets
  genuinely run side by side.
- **Serial path** otherwise: every single-ticket wave, and every wave
  when the fleet is unavailable. A mostly linear graph therefore runs
  almost entirely serially, which is correct.

## 4. Branch

An explicit `branch=` argument wins. Otherwise derive `feat/<slug>` from the
parent issue title (or the common theme of the tickets), reuse it if it
exists, and create it from the default branch if not. Check it out in the
main checkout. All tickets land on this one branch, on both paths: serial
tickets commit to it directly, and a fleet round takes it as its merge
target. The user merges it however they like afterwards.

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

- Serial path: mechanical tickets run on the cheaper model (pass
  `model: "opus"` when spawning); ordinary and foundational ones inherit
  the session model (omit `model`).
- Fleet path: mechanical maps to the `smol` slot, ordinary to `default`,
  foundational to `slow`, and UI tickets go to `ui` as herdr-fleet
  step 5 defines. `hard` is only for a ticket the user names.

If any wave takes the fleet path, run herdr-fleet sections 1 and 2 now
(slot file, preconditions, slot resolution and any integration install
question), so the plan can name each slot's active pair.

Then present the whole run as a short table and get one confirmation
before dispatching (skip the pause only if the user already told you to
run unattended): waves in order, path per wave, and per ticket its grade
plus model (serial) or slot and active pair (fleet), and the branch. This
is the last cheap moment to catch a wrong plan, and this single
confirmation is the authority for every wave and every fleet round of
the run.

## 6. The serial path

Run the wave's tickets one at a time, all on the branch in the main
checkout. For each ticket, first record the baseline: `git rev-parse HEAD`. Everything the ticket produced
is `git log <baseline>..HEAD`: commit hashes for the close comment, and
the diff for verification, taken from git, not from the subagent's
self-report.

Then spawn a `general-purpose` subagent **synchronously**
(you need its result before the next ticket) with this brief, filled in:

```
Complete <tracker> ticket #<N>: read it first with `gh issue view <N> --comments`,
and read the parent spec #<P> for context. Work on branch <branch>.
Prefer invoking the /implement skill; if unavailable, follow TDD discipline
yourself: failing test first, then implementation, in small red-green slices.
Follow the repo's conventions (CLAUDE.md / AGENTS.md), domain glossary
(CONTEXT.md), and ADRs. Run the tests you added or changed plus any affected
E2E; when green, commit with Conventional Commits (multiple commits are fine).
Return: a summary of changes (files + line refs), the exact test commands you
ran with their results, and the commit hashes. If the ticket's assumptions
contradict what you find in the code (an earlier ticket changed the ground
under it, or the work turns out to be already done), do not improvise around
the conflict: stop and return a report starting with "BLOCKED:" describing
the contradiction. Do NOT push. Do NOT close the issue: the dispatcher
closes it after verification.
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
3. Dispatch a **verifier** subagent (cheaper model) carrying the ticket's
   acceptance criteria and the baseline sha; it reads `git diff
   <baseline>..HEAD` and returns a per-criterion verdict with evidence.
   Reading the diff yourself would pull into your window exactly the source
   code this architecture exists to keep out, and the verifier, having
   written none of the code, grades it without the implementer's bias.

An implementer has every incentive to report success; re-running its commands
and grading its diff independently cost minutes, and they are what stand
between one bad ticket and five subsequent tickets built on it.

On failure: dispatch a fix-up subagent carrying the verbatim failure output
and the original brief, **escalated to the session model** if the first
attempt ran on the cheaper one; retrying a reasoning failure on the same
model mostly replays it. Budget: 2 fix-ups per ticket. If it still fails,
**stop the entire run** (never continue to later tickets on a broken
foundation), leave the branch as-is, and report exactly where and why it
stopped.

On success: close the ticket with a comment listing the commit hashes, then
move to the next.

## 7. The fleet path

Read `../herdr-fleet/SKILL.md` in full, relative to this skill's base
directory, and run one herdr-fleet round per fleet wave, sections 3
through 10, as its orchestrator. Everything that section does not
override below holds as written, including its turn, shell and context
disciplines and its one-heavy-build rule.

**Round setup** (herdr-fleet step 3):

- Round-slug: the branch slug plus `-w<k>`, within the 19-character
  limit. Package slug: `t<N>-<short>`, same limit.
- Record the wave's base: the branch HEAD at round start. The branch is
  checked out in the main checkout and is not shared or long-lived, so
  herdr-fleet's rule makes it the round's merge target directly.
- Each ticket in the wave is exactly one package: never slice, merge or
  split tickets. The step's slicing work shrinks to what the tickets
  leave open: scouts still report per ticket the files it will touch,
  its overlap with the wave's other tickets, and the convention files
  and specs to read, and they settle the merge order for overlapping
  tickets. The per-repo commands (dependency resolution, build,
  quick check, full suite) come from the first fleet round's scout
  report; carry them forward into later rounds instead of re-surveying.
  Add one question to that per-repo report: whether a single test file
  runs without a heavy build (a vitest or pytest file does; a cargo or
  xcodebuild target does not).
- A scout may raise a ticket's grade and slot, never lower it; raising
  to `hard` needs the user. A scout report that contradicts a ticket
  (the work is already done, the ground it assumes is gone) is a stale
  ticket, handled as a `BLOCKED:` question below.
- The plan confirmation is the one from section 5: present the round's
  plan table for the record and continue. Worktree decisions for
  leftovers from an earlier round still belong to the user, as
  herdr-fleet step 3 says.

**Package brief** (herdr-fleet step 5), in addition to what that step
requires:

- The ticket's full body and comments, and the parent spec, fetched by
  you and written as files in the round directory, secrets redacted.
  Implementers may run another vendor's CLI with no tracker login and no
  skills, so the brief carries everything they read.
- TDD discipline written out: failing test first, then implementation,
  in small red-green slices. The implementer still runs no heavy build
  or suite. When the scout report says a single test file runs without
  a heavy build, the brief allows running exactly the test files the
  package adds or changes, so each red-green step stays observable;
  otherwise the quick check (herdr-fleet step 8) is the first run of
  those tests.
- The stale-ticket rule: if the ticket's assumptions contradict the
  code, the implementer stops and ends its turn with a `QUESTION`
  summary whose question begins `BLOCKED:` and describes the
  contradiction.
- The issue stays open: the dispatcher closes it.

**Questions during the round.** A `BLOCKED:` question always goes to
the user, never answered from the brief, since only the user can
re-scope a ticket. The rest of the wave keeps running meanwhile, and
unless the user's answer resolves the ticket, the run stops after this
round's step 10.

**Concluding the wave.** herdr-fleet's final report (step 10) is an
interim wave report here: it ends no turn. Before step 10 deletes the
round directory, take each package's `accepted_sha` from its `state`
event on `package/<slug>/branch`. The wave has concluded when every
package merged and the suite passed on the branch's HEAD. Then close
each ticket with a comment listing
`git log --oneline <wave-base>..<accepted_sha>` and naming the branch,
and start the next wave in the same turn.

Anything short of that stops the run once the round's step 10 is done:
a dropped package, a merge the round aborted, a red suite, or an
unresolved `BLOCKED:` question. On a green suite, close the tickets
that did merge; on a red one, close none of the wave's tickets. Later
waves never start on a partial foundation.

## 8. Final sweep and report

After the last wave, dispatch one more subagent (cheaper model) to run the
repo's full check suite: lint, typecheck, full tests, full E2E, whatever the
repo's CI runs. Per-ticket runs only cover the tests each ticket touched;
cross-ticket breakage surfaces here. Skip the sweep when the last wave was
a fleet round whose suite passed on the branch's current HEAD. A failed
sweep follows the serial path's fix-up rule (session model, same budget);
if it stays red, the final report leads with that.

Then give the final report: the waves and the path each took, then per
ticket: commits, test evidence, retries or correction cycles used and why,
and, for fleet tickets, the model and CLI that actually did it. Add each
fleet round's archive path, and anything left over (TODOs, warnings, flaky
tests observed, retained worktrees).

Red lines for the whole run: never push; never modify or close the parent
spec; never skip, reorder, or merge tickets.
