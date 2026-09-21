# Refusal reasons

A refused tool call returns a tool result with `isError` and a JSON text body
`{ "error": { "code", "status", "reason", "message" } }`. Branch on `reason`.
The `message` is client-facing English that may be reworded; on read tools it
is replaced by a fixed sentence per reason. A 5xx collapses to
`INTERNAL_ERROR` with no detail; retry once, then report it.

Transport failures never become a tool call and carry no `reason`: an HTTP 401
with JSON-RPC error `-32000` means the `Authorization` header is missing, is
not `Bearer`, or the token no longer resolves. The user signs in to the panel
again and copies a fresh token from **Settings → MCP Access**.

## Organization and permissions

| Reason | Meaning | Next move |
| --- | --- | --- |
| `INVALID_ORGANIZATION_ID` | `organizationId` is not a decimal integer string. | Ask the user for the id shown in the panel. |
| `NOT_ORGANIZATION_MEMBER` | The caller is not a member of that organization. | Confirm the id with the user; no tool lists organizations. |
| `MISSING_CAPABILITY` | Read tool; the caller lacks the publishing permission it needs. | An organization administrator grants it. |
| `MISSING_PUBLISHING_CAPABILITY` | Write tool; the message names the missing permission. | Same. |
| `UPSTREAM_SESSION_EXPIRED` | The stored MuseDAM login has expired. | The user signs in to MuseDAM again. |
| `DAM_CREDENTIALS_MISSING` | No MuseDAM credential is connected for the caller. | The user signs in to MuseDAM again. |
| `MEMBERSHIP_LOOKUP_UNAVAILABLE` | MuseDAM could not be reached to confirm membership; no task was created. | Retry the create in a moment. |
| `MEMBERSHIP_WITHOUT_USER_ID` | The membership record carries no user id. | The user signs in to MuseDAM again. |

## Asset discovery

| Reason | Meaning | Next move |
| --- | --- | --- |
| `DAM_ASSET_LOOKUP_FAILED` | The DAM search failed. | Retry; if it persists the user checks their MuseDAM access. |
| `DAM_ASSET_RESPONSE_INVALID` | The DAM answered with a shape the tool cannot read. | The user checks the assets in MuseDAM; retry later. |

## Create and submit

| Reason | Meaning | Next move |
| --- | --- | --- |
| `DISPATCH_TARGET_REQUIRED` | Non-draft local task with no `desktopInstanceId`. | `list_desktop_instances`, then repeat with an `installationId`. |
| `DISPATCH_TARGET_OFFLINE` | The named instance is not online in this organization. | Pick another instance from `list_desktop_instances`. |
| `DISPATCH_TARGET_NOT_OWN` | The named instance is signed in as another member. | Pick one of the caller's own instances. |
| `TASK_RUNTIME_MIXED` | 400 `INVALID_ARGUMENT`. A stored task still names both cloud platforms and local platforms (xhs, Douyin, Kuaishou). | Open it in the MuseDAM panel and save it once so it is split into one task per runtime; the original id is replaced. Then `list_publishing_tasks` on the view the task was in (`draft` or `scheduled`): the siblings are separate rows with the same `taskName`, one per `taskRuntime` with the matching `platformTypes`. `groupTaskIds` is not on those views. The save is possible only for a draft or for a scheduled task the panel still lets the user edit: a submitted native schedule (ADR-0040) is locked, and a history row (immediate or past-due) is editable only as a resettable native-schedule failure, so for those create the task again. |
| `REELS_SCHEDULE_UNSUPPORTED` | Reels cannot be scheduled. | Use `publish_now`, or a `video` task. |
| `REELS_DRAFT_UNSUPPORTED` | Reels cannot be drafts. | Use `publish_now`, or a `video` draft. |
| `SCHEDULED_TIME_REQUIRED` | `mode` is `schedule` without `scheduledTime`. | Add it. |
| `SCHEDULED_TIME_NOT_APPLICABLE` | `scheduledTime` given with a mode other than `schedule`. | Drop it or switch mode. |
| `SCHEDULED_TIME_NOT_OFFSET_AWARE` | No UTC offset or `Z`. | Resolve the user's zone and add the offset. |
| `SCHEDULED_TIME_INVALID` | Impossible calendar date, or time or offset out of range. | Fix the date. |
| `SCHEDULE_TIME_OUT_OF_RANGE` | Less than 2 hours or more than 14 days from now. | Move it into the window, or `publish_now`. |
| `VALIDATION_FAILED` | A service-level check with no dedicated reason, media rules among them. | Read the message; it is the only guidance. |

## Retry

| Reason | HTTP code | Meaning | Next move |
| --- | --- | --- | --- |
| `RESOURCE_NOT_FOUND` | 404 | No task in this organization has this `taskId`, or the account is outside this organization. | Check both ids with `list_publishing_tasks` and `get_publishing_task`. |
| `RETRY_ACCOUNT_NOT_ON_TASK` | 404 | The account is no longer linked to the task. | Take `platformAccountId` from the task's current executions. |
| `RETRY_BROWSER_TASK_UNSUPPORTED` | 400 | Browser-runtime tasks cannot be retried. | Create a new task. |
| `RETRY_LEGACY_LOCAL_TASK_DESKTOP_ONLY` | 400 | The local task predates dispatch targets. | The creator retries it from the Desktop app. |
| `DISPATCH_TARGET_OFFLINE` | 400 | The stored Desktop target is offline. | The user edits the task in the panel to choose an online instance; then retry. |
| `DISPATCH_TARGET_NOT_OWN` | 400 | The stored Desktop target belongs to another member. | Same. |
| `NON_RETRYABLE_RESULT_UNCERTAIN` | 409 | The platform has not confirmed the latest attempt; a retry could publish twice. | Wait, read `get_publishing_task` again, retry once the execution settles. |
| `RETRY_ALREADY_IN_PROGRESS` | 409 | The latest execution is not `failed`. | Read the task; retry only a failed account. |

The retry tool has no `desktopInstanceId`. A dispatch-target refusal here is
never fixed by another argument, only by editing the task.

The retry service also defines `RETRY_TASK_NOT_FOUND` for a task id that
names no row at all. On this tool the organization check runs first and
answers an unknown id with `RESOURCE_NOT_FOUND`, so a client does not see
`RETRY_TASK_NOT_FOUND` for a bad `taskId`.
