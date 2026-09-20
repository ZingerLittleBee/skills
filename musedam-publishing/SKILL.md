---
name: musedam-publishing
description: Use when the MuseDAM Publishing MCP server is connected (tools named list_platform_accounts, list_dam_assets, list_desktop_instances, create_publishing_task, publish_publishing_task, get_publishing_task, retry_publishing_task_execution) and the user asks to post, publish, schedule, draft, inspect, or retry social media content on Xiaohongshu, Douyin, Kuaishou, TikTok, YouTube, Facebook, Instagram, X, or LinkedIn from MuseDAM assets. Not for connecting the server; the endpoint and token come from the product's own connection guide.
---

# MuseDAM Publishing

The server publishes assets that already sit in a MuseDAM library to connected
platform accounts. This skill assumes the tools already answer. Connecting a
client is covered by the product's connection guide (`docs/reference/mcp-connection.md`
in the product repository) and by the panel's **Settings → MCP Access** page;
send the user there for endpoint, token, and client snippets.

Tool arguments and result fields are in
[references/tools.md](references/tools.md). Refusal reasons and the move each
one calls for are in [references/refusals.md](references/refusals.md).

## Before the first call

- **`organizationId` comes from the user.** Every tool requires it as a decimal
  integer string, and no tool lists organizations. Ask for it if the
  conversation does not carry it; the user can read it in the panel. A guessed
  id fails with `INVALID_ORGANIZATION_ID` or `NOT_ORGANIZATION_MEMBER`.
- **Only library assets can be published.** Nothing in this API accepts file
  bytes or a URL. When the user hands you a photo from disk, a link, or a
  screenshot, tell them it has to be uploaded to MuseDAM first, then find it
  with `list_dam_assets`.
- **Only a common `title` and `description` travel.** Topics, @mentions,
  covers, locations, collections, and music are edited in the MuseDAM Desktop
  app after the task exists. Both write tools reject unknown keys rather than
  dropping them, so a call carrying `topics` fails outright. Tell the user
  which fields they will set in the Desktop app instead of promising them.

## Order of operations

1. **Accounts.** `list_platform_accounts`. Take the `id` values you will
   publish to. Status `1` is usable; `3` and `4` need the user to reauthorize
   the account first. The `status` filter applies to the current page only, so
   page through when the first page has no match.
2. **Media.** `list_dam_assets` with `keywords` or `folderIds`. Each row has
   `assetId` and `kind`. An `image_text` task takes images only; `video` and
   `reels` need at least one video. Discovery does not check platform limits
   such as size or duration.
3. **Runtime.** If any chosen account is Xiaohongshu (`xhs`), Douyin, or
   Kuaishou, the whole task runs on the user's Desktop app. A non-draft task
   for it needs `desktopInstanceId`, which is the `installationId` of an
   entry from `list_desktop_instances`. That tool lists only the caller's own
   online instances, so anything it returns is valid. If it returns nothing,
   save a draft and tell the user to open the Desktop app, or ask how they
   want to proceed. Cloud platforms (TikTok, YouTube, Facebook, Instagram, X,
   LinkedIn) take no instance; omit the field.
4. **Mode.** `draft` stores the task, `schedule` needs `scheduledTime`,
   `publish_now` submits at once. Reels accept `publish_now` only; a reel the
   user wants to prepare ahead becomes a `video` draft instead.
   `scheduledTime` is an ISO 8601 timestamp with an explicit offset or `Z`,
   for example `2026-09-21T09:00:00+08:00`, and must fall between 2 hours and
   14 days from now. A local time without an offset is refused, not
   interpreted, so resolve the user's zone before you call. `timezone` is an
   optional IANA name for display and never moves the instant.
5. **Create.** `create_publishing_task`. The result's `data.taskIds` is a
   list: one call can fan out into several tasks (Facebook splits per Page).
   Report every id. A `schedule` or `publish_now` create is already
   submitted; a `draft` is not.
6. **Submit drafts.** `publish_publishing_task` once per task id you intend
   to send, with `mode` `schedule` or `publish_now` and the same
   `scheduledTime` rules. A local task leaving draft needs an online
   `desktopInstanceId` of the caller's; omit the field to reuse the target
   already stored on the task, which is revalidated.

The connection guide's worked example shows the three JSON bodies for search,
draft, and submit; reach for it when the user wants to see the exact payloads.

## Inspecting and retrying

`list_publishing_tasks` shows the `draft`, `scheduled`, or `history` view.
`get_publishing_task` returns the task with `dispatchTarget.online` and an
`executions` list; each execution row carries `status`, `platformAccountId`,
`attemptNumber`, a safe `errorMessage`, and `platformLinks`. Diagnostics
beyond that live in the panel's publishing history.

A retry is per platform account, not per task: `retry_publishing_task_execution`
with `taskId` and a `platformAccountId` taken from the execution rows whose
latest `status` is `failed`. One account per call; loop for several. The tool
takes no instance argument. A local task retries on the Desktop target stored
on the task, so check `dispatchTarget.online` first; if that target is offline
or belongs to another member, the retry is refused and the user has to edit
the task in the panel to pick another instance, then you retry again. Passing
a different instance id is not an option on this tool.

## When a call is refused

A refusal is a tool result whose JSON is `{ "error": { "code", "status",
"reason", "message" } }`. Branch on `reason`; the message text can change.
The reasons that change your next call:

| Reason | Next call |
| --- | --- |
| `DISPATCH_TARGET_REQUIRED` | `list_desktop_instances`, then repeat with `desktopInstanceId` set to an `installationId`. |
| `DISPATCH_TARGET_OFFLINE`, `DISPATCH_TARGET_NOT_OWN` on create or submit | Same, choosing another instance. On retry there is no argument to fix it: the task is edited in the panel. |
| `SCHEDULED_TIME_NOT_OFFSET_AWARE`, `SCHEDULED_TIME_INVALID` | Rebuild `scheduledTime` with an offset and a real calendar date. |
| `SCHEDULE_TIME_OUT_OF_RANGE` | Move the time into the 2-hour to 14-day window, or switch to `publish_now`. |
| `REELS_SCHEDULE_UNSUPPORTED`, `REELS_DRAFT_UNSUPPORTED` | Reels are `publish_now` only; offer a `video` task for anything else. |
| `RETRY_ALREADY_IN_PROGRESS`, `NON_RETRYABLE_RESULT_UNCERTAIN` | Read `get_publishing_task` again and wait; nothing to retry yet. |
| `MISSING_CAPABILITY`, `MISSING_PUBLISHING_CAPABILITY` | The user lacks that publishing permission in this organization; an administrator grants it. |
| `UPSTREAM_SESSION_EXPIRED`, `DAM_CREDENTIALS_MISSING` | The user signs in to MuseDAM again; no call fixes it. |

An HTTP 401 with no `reason` never reached a tool: the bearer token is missing
or no longer resolves, and the user signs in to the panel again to get a new
one.
