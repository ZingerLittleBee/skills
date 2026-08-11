---
name: herdr-fleet
description: "Run one round of parallel implementation across multiple CLI coding agents (claude, codex, droid, grok, …) in herdr-managed git worktrees, one package per worktree ending in one PR each. Invoke with /herdr-fleet <tasks or backlog description>."
disable-model-invocation: true
---

# herdr-fleet

Complete several independent work packages in parallel by giving each one a
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
- Run `herdr agent` once to see which agent kinds are installed. Ask the user
  which subscriptions to use if they haven't said; a kind that isn't
  installed cannot be assigned.
- `gh auth status` must succeed — the round ends by pushing branches and
  opening PRs through the gh CLI, and discovering broken auth only then
  wastes the whole round.
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

Group the requested tasks into packages that can genuinely run in parallel:

- One package = one branch = one PR = one agent. Keep each package small
  enough that a single agent finishes it in one sitting.
- Minimize file overlap between packages. Where two packages must touch the
  same file, note it as a merge risk up front and decide their PR merge
  order now — a shared *base* commit merges cleanly, but two packages
  editing the same lines will not.
- Write down, per package: scope, acceptance criteria, the design or spec
  references the agent must read, and a difficulty grade.

Present the plan — packages, branch names, agent kind per package — as a
short table and get one confirmation before creating anything (skip only if
the user already said to run unattended).

## 3. One worktree per package

```bash
herdr worktree create --cwd "$PWD" --branch feat/<slug> --base <sha> --label <slug> --no-focus
```

Pin every package to the same `--base` commit (the default branch's head at
round start) and record that sha: it keeps packages from drifting apart if
the default branch moves mid-round, and it is the **baseline** every later
verification diffs against.

Read the workspace id and root pane id from the JSON. Then make the worktree
actually buildable before starting an agent in it:

- **Binary artifacts don't follow.** Git worktrees share history, not
  ignored build artifacts. If the build depends on a large local artifact
  (a prebuilt xcframework, a vendored binary), copy the real directory into
  the worktree — symlinks often defeat build systems that resolve artifact
  identity through the path.
- Run the project's dependency resolution step in the worktree once
  (e.g. `swift package resolve`, `pnpm install`); retry on transient
  network failures rather than concluding the worktree is broken.

## 4. Assign agents by difficulty

Map difficulty to the user's subscriptions, strongest kind to the hardest
package. Foundational or architecturally risky packages get the strongest
agent — a weak foundation costs every reviewer and every later round.
Mechanical, well-bounded packages (apply an established pattern, styling
sweeps, copy changes) go to the cheaper kinds. When unsure, assign up.

```bash
herdr agent start <slug> --kind <kind> --pane <root-pane-id>
```

Name each agent after its package slug so `herdr agent list` reads as a
status board.

## 5. Brief each agent

A real brief is too long to push through a terminal. Write it as a Markdown
file in the OS temp directory — one per package, e.g.
`$TMPDIR/herdr-fleet-<slug>.md` — and make the prompt a one-liner pointing
at it:

```bash
herdr agent prompt <slug> "Read $TMPDIR/herdr-fleet-<slug>.md and complete the package it describes."
```

Long text sent through `agent prompt` risks wrapping and paste-mode
mangling, and a file survives for re-briefing after a crash or a swallowed
prompt. This is the **file-drop** rule, and it covers everything long you
send an agent all round — briefs, review feedback, failing build output:
write a temp file, send the path. Write the file with the same discipline
as a handoff document:
self-contained, referencing specs and code by path instead of inlining
them, and with secrets redacted — the agent's pane is visible to anyone at
the screen.

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

Between briefing and the last PR, the orchestrator's whole job is the watch
loop. Do not end the turn to "wait for the agents", and do not drift into
side work — an unwatched fleet stalls: a `blocked` agent burns wall-clock
until someone answers it, and a crashed agent silently drops its package.

Loop until every package has settled:

```bash
sleep 60; herdr agent list
```

Keep a per-package status board — agent state, last state change, review
rounds used, next action — and update it on every poll. When an agent
changes state, read its recent output before deciding anything:

```bash
herdr agent read <name> --source recent-unwrapped --lines 120
```

Priorities inside the loop: answer `blocked` agents first (each is stalled
wall-clock), then review settled ones (step 7), then check long-`working`
ones — an agent whose output hasn't changed across several polls may be
stuck on an unrecognized prompt or spinning; read the pane and decide.
Surface progress to the user at transitions that matter (package settled,
review sent, validation passed, PR opened), not on every poll.

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
  report to a temp Markdown file and reply with only the path, then read
  the file directly.
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
brief wasn't followed even if the summary reads well.

Then spawn a **reviewer subagent** to grade the diff — do not read it
yourself. Package diffs pulled into the orchestrator window are exactly
the source this architecture keeps out: by the fourth package your
judgment is swimming in the first three's implementation noise, and having
briefed the round you also want it to succeed — a reviewer that wrote none
of it grades without that bias. The reviewer needs only three inputs: the
brief file path, the worktree path, and the base sha. It reads
`git diff <base-sha>..HEAD`, returns a per-criterion verdict with
evidence, and flags anything outside the brief's scope. Reviews are
read-only, so several can run in parallel while other agents are still
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
feedback is a file-drop (step 5).
Budget 2 review rounds per package, then either accept with documented
caveats or drop the package from the round and say why. A dropped
package's worktree and branch stay in place for the user to inspect — its
work exists nowhere else — but its agent gets shut down like any finished
one (step 9).

## 8. Validate serially

Only after a package passes review, run the repo's real build and test
commands **in that worktree, one worktree at a time** — never two at once.
On failure, send the owning agent the verbatim failing output (not your
paraphrase) and re-validate after the fix; long output is a file-drop
(step 5).

## 9. One PR per package

Invoking this skill is the authorization to push the package branches and
open their PRs; merging stays with the user. For each validated package:

```bash
git -C <worktree> push -u origin feat/<slug>
gh pr create --head feat/<slug> --title "<conventional title>" --body "<summary + test evidence>"
```

PR titles and bodies in English, Conventional-Commit style titles, no
watermarks. If two packages touch the same files, state the agreed merge
order in both PR bodies and in your report — the later PR gets rebased once
the earlier one lands, rather than trusting the three-way merge.

**Then shut the finished agent down promptly.** An agent left running after
its package is done keeps a live session holding your repo context and
credentials, keeps occupying a subscription seat, and will act on any stray
input that reaches its pane. Ask it to quit with its own exit command
(`/exit`, `/quit`, or ctrl+c / ctrl+d via `herdr agent send-keys`), then
confirm the name is gone from `herdr agent list` and the pane is back at a
shell prompt. Keep the pane and the worktree — if PR feedback later needs
fixes, start a fresh agent in the same pane and point it at the brief file
plus the committed diff.

Report all PR URLs to the user and stop — do not merge.

## 10. After the merge: clean up and re-verify

When the user says the PRs are merged:

1. Confirm it per PR: `gh pr view <n> --json state` must report `MERGED`.
   This is the authority regardless of merge strategy — a squash merge
   rewrites the package commits, so "commits not reachable from the
   default branch" is **not** evidence of unmerged work once the PR
   reports MERGED.
2. Pull the default branch in the main repo.
3. Remove each worktree whose PR is MERGED:
   `herdr worktree remove --workspace <id> --force`. A worktree whose PR
   is not merged and whose commits exist nowhere else never gets
   force-removed; surface it instead.
4. Delete the local package branches — worktrees first, branches second:
   git refuses to delete a branch that is still checked out in a
   worktree. After a squash merge `git branch -d` still counts the branch
   unmerged, so use `-D` once step 1 confirmed the PR. Then
   `git fetch --prune` to confirm the remotes are gone.
5. Run the full validation suite once on merged main — per-package runs
   don't cover cross-package interaction; this is where it shows up.
6. Final report: per package — branch, PR, review rounds used, validation
   evidence — plus anything left over.

Round invariants: implementation belongs to the agents and diff-grading to
the reviewers; exactly one heavy build runs at a time; the orchestrator
pushes and the user merges; a worktree holding unmerged work stays in
place; a finished agent gets shut down.
