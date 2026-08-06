---
name: herdr-fleet
description: "Run one round of parallel implementation across multiple CLI coding agents (claude, codex, droid, grok, …) in herdr-managed git worktrees. The main session is a pure orchestrator: it packages the backlog, creates one worktree per package, assigns each package to an agent kind by difficulty, monitors and reviews, validates serially, opens one PR per package, and removes worktrees after merge. Invoke with /herdr-fleet <tasks or backlog description>."
disable-model-invocation: true
---

# herdr-fleet

Complete several independent work packages in parallel by giving each one a
git worktree and a dedicated CLI coding agent inside herdr. You are the
**orchestrator**: you slice the work, brief the agents, watch their state,
review their diffs, and run validation. You never implement — every source
edit happens inside an agent's worktree. That split is what makes the round
safe: your context stays small enough to review package N honestly after
babysitting packages A through M, and no two writers ever share a checkout.

## 1. Preconditions

- Confirm you are inside a herdr-managed pane: `test "${HERDR_ENV:-}" = 1`.
  If not, say so and stop — do not drive herdr from outside herdr.
- The main repo's working tree must be clean (`git status`); surface a dirty
  tree instead of working around it.
- Run `herdr agent` once to see which agent kinds are installed. Ask the user
  which subscriptions to use if they haven't said; a kind that isn't
  installed cannot be assigned.
- This is a long, hands-off run. If the session isn't in an auto-accepting
  permission mode, warn that every approval prompt stalls the round.

herdr CLI basics that the whole flow relies on: control commands return
JSON — read every workspace/tab/pane id from the response
(`.result.workspace`, `.result.root_pane.pane_id`, …), never guess them.
Agent states: `working` (leave it alone), `blocked` (it needs input),
`idle`/`done` (turn finished), `unknown` (present but unclassified — not
proof of completion).

## 2. Package the work

Group the requested tasks into packages that can genuinely run in parallel:

- One package = one branch = one PR = one agent. Keep each package small
  enough that a single agent finishes it in one sitting.
- Minimize file overlap between packages. Where two packages must touch the
  same file, note it as a merge risk up front — a shared *base* commit
  merges cleanly, but two packages editing the same lines will not.
- Write down, per package: scope, acceptance criteria, the design or spec
  references the agent must read, and a difficulty grade.

Present the plan — packages, branch names, agent kind per package — as a
short table and get one confirmation before creating anything (skip only if
the user already said to run unattended).

## 3. One worktree per package

```bash
herdr worktree create --cwd "$PWD" --branch feat/<slug> --label <slug> --no-focus
```

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

Send the brief with `herdr agent prompt <name> "<brief>"`. Do **not** use
`--wait` — these are long turns; you'll poll instead. The brief must carry:

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

## 6. Monitor the round

Poll `herdr agent list` on a relaxed cadence; when an agent changes state,
read its recent output:

```bash
herdr agent read <name> --source recent-unwrapped --lines 120
```

Known traps and how to handle them:

- **Swallowed first prompt.** Some agents (droid, notably) eat a prompt sent
  during their startup/welcome screen. If an agent is `idle` shortly after
  start with no meaningful output, re-send the brief.
- **`blocked`** means the agent is showing an approval or question UI. Read
  the screen before acting; answer with `herdr agent prompt` for free-text
  questions or `herdr agent send-keys <name> <key>` for menu-style prompts.
- Never send a new prompt to a `working` agent — it lands mid-turn and
  corrupts the run. Wait for `idle`/`done`/`blocked`.

## 7. Review each package

When an agent settles, review its work yourself in the worktree — read
`git log`/`git diff` against the package's acceptance criteria and the
design references. You read; you never edit. Send findings back as a
numbered review prompt and wait for the fix. Loop until the diff is clean;
budget 2 review rounds per package, then either accept with documented
caveats or drop the package from the round and say why.

Verify with git, not with the agent's self-report: uncommitted leftovers in
the worktree mean the brief wasn't followed even if the summary reads well.

## 8. Validate serially

Only after a package passes review, run the repo's real build and test
commands **in that worktree, one worktree at a time** — never two at once.
On failure, send the owning agent the verbatim failing output (not your
paraphrase) and re-validate after the fix.

## 9. One PR per package

Invoking this skill is the authorization to push the package branches and
open their PRs; merging stays with the user. For each validated package:

```bash
git -C <worktree> push -u origin feat/<slug>
gh pr create --head feat/<slug> --title "<conventional title>" --body "<summary + test evidence>"
```

PR titles and bodies in English, Conventional-Commit style titles, no
watermarks. Report all PR URLs to the user and stop — do not merge.

## 10. After the merge: clean up and re-verify

When the user says the PRs are merged:

1. Pull the default branch in the main repo.
2. Delete the local package branches; confirm the remote branches are gone
   (`git fetch --prune`).
3. Remove each worktree: `herdr worktree remove --workspace <id> --force` —
   but only after confirming its commits are reachable from the merged
   default branch. A worktree holding unmerged unique commits never gets
   force-removed; surface it instead.
4. Run the full validation suite once on merged main — per-package runs
   don't cover cross-package interaction; this is where it shows up.
5. Final report: per package — branch, PR, review rounds used, validation
   evidence — plus anything left over.

Red lines for the whole round: the orchestrator never edits source; never
run two heavy builds concurrently; never merge a PR; never force-remove a
worktree with unmerged work; never let an agent push.
