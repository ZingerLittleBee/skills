# Tool reference

Facts that the tool schemas do not carry, per tool. Every tool takes
`organizationId` as a decimal integer string and refuses a non-member with
`NOT_ORGANIZATION_MEMBER`. Capabilities are the publishing permissions the
caller must hold in that organization; a missing one is refused with
`MISSING_CAPABILITY` on read tools and `MISSING_PUBLISHING_CAPABILITY` on write
tools. A successful result is a JSON text block `{ "data": ... }`, followed on
most tools by a one-line summary text block.

## `list_platform_accounts`

Required: `organizationId`. Optional: `page`, `pageSize`, `platform`, `status`,
`alias`, `search`. Capability: `view_content`.

Rows: `id` (the value for `platformAccountIds`), `platformType`, `displayName`,
`status`, `sessionActionReason`, `groupId` (`null` when ungrouped).

- Status values: `0` disabled, `1` usable, `2` unknown, `3` expired (a refresh
  can recover it, and this listing may perform that refresh), `4` needs
  reauthorization (refresh failed or the platform has no refresh).
- The `status` filter is applied to the page already fetched, so
  `pagination.total` stays the unfiltered total. Advance pages to find more.
- Calling it has side effects: stale OAuth placeholder accounts are deleted and
  session health checks may refresh credentials.

## `list_desktop_instances`

Required: `organizationId`. Capability: `create_content`.

Rows: `installationId` (the value for `desktopInstanceId`), `hostname`,
`osName`, `osVersion`, `cpuArch`, `appVersion`, `memberName`, `lastSeenAt`.

- Lists only the caller's own online instances in that organization, so every
  row is a valid target.
- Personal spaces return an empty list.

## `list_dam_assets`

Required: `organizationId`. Optional: `keywords`, `folderIds`, `page` (default
1), `pageSize` (default 20, max 100). Capability: `create_content`.

Rows: `assetId`, `name`, `extension`, `kind` (`image` or `video`), `width`,
`height`, `duration` (milliseconds).

- Pass `assetId` and `kind` straight into `media` on
  `create_publishing_task`, with the same `organizationId`.
- `total` is `null` when the DAM omits a count; `hasMore` only means the
  upstream page was full.
- Rows whose extension is not a supported image or video are skipped and
  counted in the summary.
- Discovery does not check platform limits (size, duration, aspect ratio).
- There is no upload tool. Bytes and URLs cannot enter the library through
  this API.

## `create_publishing_task`

Required: `organizationId`, `publishType` (`image_text`, `video`, `reels`),
`mode` (`draft`, `schedule`, `publish_now`), `platformAccountIds` (at least
one), `media` (at least one `{ "assetId": <number>, "kind": "image" | "video" }`).
Optional: `title`, `description`, `scheduledTime`, `timezone`,
`desktopInstanceId`. Capability: `create_content`.

Result `data`: `taskIds` (a list), `publishType`, `mode`, `taskRuntimes` (a
map from each task id to `local` or `cloud`), `taskExecutionType`,
`scheduledTime`, `timezone`, `dispatchTargetInstanceId`. When every created
row shares one runtime, `taskRuntime` is also present and equals that
shared value. When the rows span two runtimes, `taskRuntime` is omitted
entirely (not null): no single value is true of both rows. Read `taskRuntimes`
for the per-row truth.

- The input schema is strict: any key outside the list above is refused, so
  platform-specific fields (topics, @mentions, covers, locations, collections,
  music) cannot be smuggled in. They are edited in the Desktop app afterwards.
- `image_text` accepts images only; `video` and `reels` need at least one
  video.
- Reels: `mode` must be `publish_now` (`REELS_SCHEDULE_UNSUPPORTED`,
  `REELS_DRAFT_UNSUPPORTED`).
- `scheduledTime` is required for `schedule` and refused for any other mode
  (`SCHEDULED_TIME_REQUIRED`, `SCHEDULED_TIME_NOT_APPLICABLE`). It must carry
  an explicit offset or `Z`, name a real calendar date, and fall between
  2 hours and 14 days from now (`SCHEDULED_TIME_NOT_OFFSET_AWARE`,
  `SCHEDULED_TIME_INVALID`, `SCHEDULE_TIME_OUT_OF_RANGE`).
- `timezone` is an optional IANA name and never changes the instant. It is
  stored only for a scheduled or immediate image or video task; a draft stores
  no timezone and a reels create ignores it. The result echoing `timezone` is
  not proof that it was stored.
- The runtime follows the platform. Facebook, Instagram, X, YouTube, TikTok,
  and LinkedIn always publish in the cloud. Xiaohongshu (`xhs`), Douyin, and
  Kuaishou always publish on a Desktop instance. A create that names both
  groups produces one task per runtime under one group. A local task
  with `mode` `schedule` or `publish_now` needs an online `desktopInstanceId`
  owned by the caller; a draft never does. Cloud tasks ignore the field.
- One call can create several tasks: Facebook splits per Page, and a mix of
  cloud platforms with Xiaohongshu, Douyin, or Kuaishou creates one task per
  runtime. A create that names two Facebook Pages and one Xiaohongshu
  account produces three tasks under one group (one per Page, plus the
  Xiaohongshu task). Every id in `taskIds` is a separate task to submit,
  inspect, or retry.

## `publish_publishing_task`

Required: `organizationId`, `taskId`, `mode` (`schedule`, `publish_now`).
Optional: `scheduledTime`, `timezone`, `desktopInstanceId`. Capability:
`schedule_publish` for `schedule`, `publish_now` for `publish_now`.

- Submits an existing task, typically a draft from `create_publishing_task`.
  Content is untouched; only the execution type, scheduled time, timezone, and
  Desktop dispatch target change.
- `scheduledTime` follows the same rules as on create, window included.
- A local task leaving draft needs an online `desktopInstanceId` owned by the
  caller. A draft stores no target, so omitting the field on a draft is
  refused with `DISPATCH_TARGET_REQUIRED`. Omitting it on a task that already
  carries a target reuses that target and revalidates it.
- Publishing or scheduling a task whose accounts still span both runtimes is
  refused (`TASK_RUNTIME_MIXED`). Open it in the MuseDAM panel and save it
  once so it is split into one task per runtime; the original id is replaced.
  `list_publishing_tasks` on the view the task was in (`draft` or
  `scheduled`) then shows the siblings as separate rows with the same
  `taskName`, one per `taskRuntime` with the matching `platformTypes`.
  `groupTaskIds` is not on those views; it is filled only on `history`.
  The save is possible only for a draft or for a scheduled task the panel
  still lets the user edit: a submitted native schedule (ADR-0040) is locked,
  and a history row (immediate or past-due) is editable only as a resettable
  native-schedule failure that still has a `taskRuntime` (a history group
  whose `taskRuntime` is absent cannot be edited at all), so for those create
  the task again.

## `list_publishing_tasks`

Required: `organizationId`, `view` (`draft`, `scheduled`, `history`).
Optional: `page`, `pageSize`. Capability: `view_analytics` for `history`,
otherwise `view_content`.

Rows: `id`, `taskName`, `platformAccountIds`, `platformTypes`, `publishType`,
`taskRuntimes`, `taskExecutionType`, `createdAt`, `scheduledTime`,
`scheduledTimezone`, `publishedAt`, `publishedAtTimezone`, `lastExecutionAt`,
`executionResult` (counts by status), `dispatchTarget`, `groupTaskIds`
(`history` only; absent on `draft` and `scheduled`). `taskRuntime` is present
only when every task in the row shares one runtime.

- `history` is not only completed tasks: it includes immediate tasks,
  terminal executions, and past-due scheduled tasks. Its `pagination.total`
  counts publish-action groups, not raw tasks.
- Runtime fields follow the `create_publishing_task` shape. `taskRuntimes` is
  always present and maps each task id in the row to that task's runtime,
  normally `local` or `cloud`; a task created before runtimes followed the
  platform may still read `browser`, which a client treats as not cloud
  rather than as an error. On `draft` and `scheduled` the map has the row's
  own id as its only key. A `history`
  row folds one publish-action group, so it may hold a cloud task and a local
  task (two Facebook Pages plus one Xiaohongshu account is three tasks:
  cloud, cloud, local). When every task in the row shares one runtime,
  `taskRuntime` is also present and equals that value. When they span two
  runtimes, `taskRuntime` is omitted entirely (not null): no single value is
  true of the row. `platformTypes`, `executionResult`, and `dispatchTarget`
  are folded across the group; the Dispatch Target is the local task's, and
  the cloud tasks carry none. Read `taskRuntimes` for the per-task truth and
  `get_publishing_task` for one task.

## `get_publishing_task`

Required: `organizationId`, `taskId`. Capability: `view_content` and
`view_analytics`.

Result: `id`, `taskName`, `platformAccountIds`, `publishType`, `taskRuntime`,
`taskRuntimes`, `taskExecutionType`, `createdAt`, `updatedAt`,
`scheduledTime`, `desktopInstanceId`, `dispatchTarget` (`installationId`,
`hostname`, `online`, `lastSeenAt`, or `null`), `content` (common title and
description plus DAM media references), `executions`. One task is one
runtime, so `taskRuntime` is always present here and `taskRuntimes` maps the
task's own id to the same value, in the shape the list and create tools use.

Execution rows: `id`, `status`, `platform`, `platformAccountId` (`null` when
the account was deleted), `attemptNumber`, `createdAt`, `updatedAt`,
`errorMessage` (a fixed safe summary, never the platform's text),
`platformLinks` (`platform`, `url`, `source`).

- Reading a task has side effects: it updates timeouts, recovers pending
  receipts, and triggers reconciliation. That is why a retry refused as
  uncertain asks you to read the task again before trying.
- Platform links keep only public content ids; credential-bearing query
  parameters are stripped.

## `retry_publishing_task_execution`

Required: `organizationId`, `taskId`, `platformAccountId`. Capability:
`publish_now`.

Result `data`: `taskId`, `platformAccountId`, `executionId`, `attemptNumber`,
`status`, `triggeredBy` (`cloud`, or a local Desktop poll).

- Retries one account's failed execution on one task. There is no whole-task
  retry; call once per failed account.
- `platformAccountId` comes from the task's current execution rows; retry only
  an account whose latest execution has `status` `failed`.
- No `desktopInstanceId` argument. A local task reuses the dispatch target
  stored on it; an offline or foreign target is refused and the task is
  edited in the panel to change it.
