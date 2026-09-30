# Held-out acceptance set

These cases are the final acceptance check for the herdr-fleet skill. They
are never used to choose, tune or compare variants during iteration:

- They run only in the flow `herdr-fleet-heldout`. `hfeval run` refuses a
  held-out case in any other flow, and refuses iteration cases in this one.
- `all_cases()` (the iteration set) never lists them.
- Their task texts (`_shared/tasks.yaml`), hidden tests (`_shared/hidden/`)
  and catalogs (`catalogs/`) are separate from the iteration set's.

Run them once for the baseline and once for a final candidate. Do not read
their per-case traces while iterating on the skill.

| Case | Fault | Mechanism |
|---|---|---|
| H1 | an implementer's process dies mid-task | Injector `kill_agent`: once a package implementer has been `working` for 75 s, SIGKILL its pane's foreground process group (only if it descends from the attempt's herdr server). |
| H2 | a reviewer's verdict file is malformed | Injector `corrupt_verdict`: the first complete `*verdict*.json` is truncated to half its bytes while its reviewer is still `working`. |
| H3 | the review slot is exhausted | Catalog `review-dead`: openai implementers, a single dead anthropic review model. Before the first user reply the harness writes `review-dead-fixed` (adds `claude-sonnet-5-medium`). |
| H4 | the orchestrator is cut off mid-round | Once a worktree has a commit and an agent is `working`, the orchestrator's process group is killed; after 240 s it is resumed with a usage-limit message. Not a user turn. |
| H5 | two requests contradict each other | `sort_amount` and `sort_first_seen` cannot both hold; `stats` is independent filler and the only outcome module. |
| H6 | a catalogued CLI is not installed | Catalog `missing-cli`: `gemini` kind first for two models. The run refuses to start if `gemini` is on PATH. |

Grading details are in `../../metrics.md` ("Held-out set"). The graders are
exercised on synthetic rounds and stand-in processes in
`selftests/test_heldout.py`; those checks are simulated evidence only.
