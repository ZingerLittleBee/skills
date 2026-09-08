# Web testing

Use this reference for `target_kind: web`. The routing table in `SKILL.md`
selects one browser driver for the run; tool failures are blockers, not a reason
to silently switch drivers.

## Driver responsibilities

- Include the required login state, account role, and test data setup in the
  plan. Ego task spaces inherit login state by default; a new space does not
  establish a logged-out baseline. Testing login itself requires a verified
  logged-out test context. Do not clear or log out the user's normal session
  to obtain one. Escalate when the required initial state cannot be established.
- Keep `.testloop/browser-session.json` across rounds and escalation follow-ups.
  Include its absolute path and the prompt blocks below in each tester prompt.
  Reuse a recorded session for the same goal if it still exists; a fresh Codex
  tester is not a request for a fresh browser. For a separate run, start new
  bookkeeping only after the previous session has been finalized.
- Route browser handoffs through `decision.json` and the existing human-answer
  path. While waiting for human input, preserve the browser, app, and tester
  pane. Pass the exact answer to the tester; only explicit confirmation to
  continue authorizes regaining browser control.
- During wrap-up, finalize only the recorded run-owned session. For ego, load
  its installed skill, confirm the run has ended in one heredoc, then call
  `completeTaskSpace(id, { keep: false })` in a separate final heredoc and check
  `done`. Follow its ownership rules; do not reclaim a user-owned space just to
  clean it up. Keep a space only for the concrete cases allowed by that skill,
  and report any skipped or blocked cleanup. For agent-browser, close only the
  recorded session with `agent-browser --session <session-name> close`.

## Shared tester prompt block

Substitute `<abs>` as in the main prompt template.

```text
Read <abs>/.testloop/browser-session.json if it exists and resume that run's
browser session. If its driver differs from the selected tool, stop and escalate.
Otherwise, when no record exists, create a session for this testloop goal and write
only its driver and identifier to that file, using the schema below. Never
store cookies, tokens, or account details there. If the recorded session is
missing, verify that before creating a replacement and report why it changed.

Verify the plan's required login state and test data before executing its steps.
An inherited login does not prove the login flow works. After the app is rebuilt,
reload the app page and verify readiness before testing the new round. Browser
state and server data may persist; use the plan's setup steps for repeatability.
Perform tested actions through the UI; do not bypass them with fetch calls,
direct app APIs, or JavaScript that changes application state.

This tester turn is one round of an ongoing goal. Leave the browser session
available after writing results; the driver owns final run cleanup.
```

## Ego tester prompt block

```text
Read the installed ego-browser skill. Run browser operations through
`ego-browser nodejs` heredocs. When no session is recorded, create a task space
named for this testloop goal with useOrCreateTaskSpace; record its returned
numeric id as {"driver":"ego-browser","task_space_id":123}, replacing 123
with the actual id. In later heredocs and rounds,
select that exact id with useOrCreateTaskSpace, subject to the skill's ownership
rules. Keep the same space through corrections and retests.

When manual input is needed, handOffTaskSpace(id), write decision.json with the
required action, and stop. If the user takes control, or the space is inactive
or unassigned, stop and escalate without retrying or creating another space.
After explicit confirmation to continue, follow the skill's takeOverTaskSpace
or claimTaskSpace path for the reported ownership state, then observe again.
```

## Agent-browser tester prompt block

```text
Read the installed agent-browser skill and run `agent-browser skills get core`
before driving the page. When no session is recorded, create a uniquely named
session and record {"driver":"agent-browser","session_name":"<unique-session-name>"},
and pass that exact name with --session on every browser command. Resume it in
later rounds. Follow the plan's login setup; do not import unrelated auth state.
```
