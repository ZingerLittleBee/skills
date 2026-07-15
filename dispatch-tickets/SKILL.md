---
name: dispatch-tickets
description: "Run a set of tracker tickets to completion in one session: the main agent is a dispatcher that never implements, spawning a fresh implementer subagent per ticket in dependency order, verifying each result, and closing tickets as it goes. Simple tickets go to a cheaper model. Invoke with /dispatch-tickets #N #N … or /dispatch-tickets parent=#N [branch=…]."
disable-model-invocation: true
---

# dispatch-tickets

Complete a set of tickets in a single session by dispatching one subagent per
ticket. You are the **dispatcher**: you order the work, brief the implementers,
verify their output, and close tickets. Your own hands touch only the
tracker, git plumbing, and test commands — implementation, including reading
source, happens exclusively inside subagent windows. That division is the whole reason this
architecture works: each subagent starts with a fresh context window, so
ticket N's implementation noise can never contaminate ticket N+1, and a
dispatcher window kept free of source code stays sharp on the last ticket too.

## 1. Preconditions

- Working tree must be clean (`git status`); a dirty tree makes verification
  and commit attribution impossible. Stop and surface it.
- This is a long, hands-off run in which subagents edit files and run
  commands continuously. If the session is not in an auto-accepting permission
  mode, tell the user each approval prompt will stall the run, and let them
  restart in a suitable mode before you begin.
- If the repo declares its tracker conventions (e.g. `docs/agents/issue-tracker.md`),
  follow those. Default: GitHub issues via the `gh` CLI.

## 2. Gather and order the tickets

Accept either an explicit ticket list (`#319 #320 …`) or `parent=#N`, in which
case discover the children: native sub-issues first, otherwise open issues
whose body references the parent.

Read every ticket in full (`gh issue view <n> --comments`), and the parent
spec if there is one — you need each ticket's acceptance criteria to verify
later, and the parent for tie-breaking questions.

Build the dependency graph from the tracker's native blocking relations
(`issue_dependencies_summary.blocked_by` on GitHub), falling back to
`Blocked by:` lines in ticket bodies. Topologically sort and execute **strictly
serially** in that order — all tickets share one branch and one working tree,
so parallel implementers would trample each other. Never trust the order the
arguments were written in; the graph is the truth. If the graph has a cycle,
or a ticket is blocked by an open issue outside the given set, stop and ask.

## 3. Branch

An explicit `branch=` argument wins. Otherwise derive `feat/<slug>` from the
parent issue title (or the common theme of the tickets), reuse it if it
exists, and create it from the default branch if not. All tickets land on this
one branch; the user merges it however they like afterwards.

## 4. Assign a model per ticket

Classify each ticket before starting:

- **Cheaper model** (pass `model: "opus"` when spawning) — mechanical work
  with crisp boundaries: prefactors, deletion/cleanup sweeps, applying an
  established pattern to more call sites, i18n/config chores.
- **Session model** (omit `model`) — anything the other tickets build on
  (skeletons, new architecture), anything stateful or lifecycle-heavy, and
  anything the parent spec flags as risky.

Foundations fail expensively — every later ticket inherits their flaws — so
when unsure, inherit the session model; the savings on a misjudged ticket are
not worth the rework.

Then present the plan — execution order, model per ticket, branch — as a short
table and get one confirmation before dispatching (skip the pause only if the
user already told you to run unattended). This is the last cheap moment to
catch a wrong plan.

## 5. The dispatch loop

For each ticket in order, first record the baseline: `git rev-parse HEAD`.
Everything the ticket produced is `git log <baseline>..HEAD` — commit hashes
for the close comment, and the diff for verification — taken from git, not
from the subagent's self-report.

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
the conflict — stop and return a report
starting with "BLOCKED:" describing the contradiction. Do NOT push. Do NOT
close the issue — the dispatcher closes it after verification.
```

A "BLOCKED:" return is not a failure — it means the ticket is stale. Stop the
run and surface the contradiction to the user; re-briefing an implementer to
guess its way around a wrong ticket produces confident garbage.

When the subagent returns, **verify yourself — never trust the report**:

1. `git log <baseline>..HEAD` shows new commits, and `git status` is clean
   again — uncommitted leftovers mean the brief wasn't followed, which is a
   failure even if tests pass.
2. Re-run the test commands the subagent reported; they must actually pass.
3. Dispatch a **verifier** subagent (cheaper model) carrying the ticket's
   acceptance criteria and the baseline sha; it reads `git diff
   <baseline>..HEAD` and returns a per-criterion verdict with evidence.
   Reading the diff yourself would pull into your window exactly the source
   code this architecture exists to keep out — and the verifier, having
   written none of the code, grades it without the implementer's bias.

An implementer has every incentive to report success; re-running its commands
and grading its diff independently cost minutes, and they are what stand
between one bad ticket and five subsequent tickets built on it.

On failure: dispatch a fix-up subagent carrying the verbatim failure output
and the original brief, **escalated to the session model** if the first
attempt ran on the cheaper one — retrying a reasoning failure on the same
model mostly replays it. Budget: 2 fix-ups per ticket. If it still fails,
**stop the entire run** — do not continue to later tickets on a broken
foundation — leave the branch as-is, and report exactly where and why it
stopped.

On success: close the ticket with a comment listing the commit hashes, then
move to the next.

## 6. Final sweep and report

After the last ticket, dispatch one more subagent (cheaper model) to run the
repo's full check suite — lint, typecheck, full tests, full E2E, whatever the
repo's CI runs. Per-ticket runs only cover the tests each ticket touched;
cross-ticket breakage surfaces here. A failed sweep follows the same fix-up
rule as a failed ticket (session model, same budget); if it stays red, the
final report leads with that.

Then give the final report: per ticket — commits, test evidence, retries used
and why; plus anything left over (TODOs, warnings, flaky tests observed).

Red lines for the whole run: never push; never modify or close the parent
spec; never skip, reorder, or merge tickets.
