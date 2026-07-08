---
name: implement-codex
description: "Implement a PRD or set of issues by delegating the coding to Codex (xhigh reasoning): Claude briefs, verifies, reviews, and commits."
disable-model-invocation: true
---

# implement-codex

Implement the work described in the PRD or issues by delegating the coding to
Codex. You are the **harness**: you brief Codex, verify its output, and commit.
Codex is the implementer — do not write the implementation yourself until the
hand-back budget below is spent.

## 1. Brief

Require a clean working tree (`git status`) before anything else — a dirty
tree makes diff attribution and the final commit impossible. If it is dirty,
stop and surface it.

Create a per-run scratch directory — `mktemp -d /tmp/implement-codex.XXXXXX` —
and keep every scratch file below inside it (written as `<scratch>/…`), so
concurrent runs never overwrite each other.

Read the PRD or issues in full and enumerate the work items, each with its
acceptance criteria. Write the brief to `<scratch>/brief.md` containing:

- the work items and their acceptance criteria
- repo conventions Codex must follow (point it at CLAUDE.md / AGENTS.md when present)
- the verification commands (typecheck, test suite) and the instruction to run
  them before finishing
- "Do NOT commit — the harness commits."
- "Report in English — your final message is read by the harness, not the
  user, and it overrides any language preference in your global config."

## 2. Implement

Run Codex in the background and watch the log:

```bash
cat <scratch>/brief.md | codex exec --yolo -c model_reasoning_effort=xhigh \
  -o <scratch>/last-message.md 2>&1 | tee <scratch>/codex.log
```

Long runs are normal at xhigh; follow progress with
`tail -f <scratch>/codex.log`. If the process exits almost immediately,
the CLI likely failed to start — read the log tail before assuming any work
happened.

When it finishes, read `<scratch>/last-message.md` for Codex's final report
and capture the session id printed near the top of the log — hand-backs
resume it.

## 3. Verify

Run typechecking and the full test suite yourself — never trust Codex's claim
that they pass. Then walk the brief against the working tree — `git status`
plus `git diff` (new files are untracked and invisible to plain `git diff`):
every acceptance criterion is either implemented and tested, or recorded as a
failure.

On any failure, hand back: write the failure output to
`<scratch>/handback.md` and resume the session captured in step 2 —

```bash
cat <scratch>/handback.md | codex exec resume <session-id> --yolo \
  -c model_reasoning_effort=xhigh -o <scratch>/last-message.md - 2>&1 \
  | tee -a <scratch>/codex.log
```

Resume by explicit session id, not `--last` — any other Codex run in this repo
in between would steal `--last`. After each hand-back, re-run this step from
the top.

Budget: 3 hand-backs. Only after the budget is spent may you fix the remainder
by hand.

## 4. Review and commit

Use /code-review on the diff. Feed substantive findings back through a
hand-back (same budget, same re-verify); fix trivial ones directly.

Then commit to the current branch, defaulting to one commit per work item:
stage each item's files separately. Small related items may share a commit,
and genuinely inseparable changes must — just never mix changes a single
message can't honestly cover.

Done means: every work item verified against its acceptance criteria, the full
suite green, review findings addressed, and every work item committed.
