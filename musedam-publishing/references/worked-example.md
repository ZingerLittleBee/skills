# Worked example

One image post: find the asset, save a draft, submit it. Use the real
`organizationId` from the user and account ids from `list_platform_accounts`.
Every body below is the complete argument object for that tool.

## 1. Search the library

`list_dam_assets`:

```json
{
  "organizationId": "1001",
  "keywords": "campaign",
  "page": 1,
  "pageSize": 20
}
```

Take an `assetId` whose `kind` is `image`.

## 2. Create a draft

`create_publishing_task`:

```json
{
  "organizationId": "1001",
  "publishType": "image_text",
  "mode": "draft",
  "title": "Spring lookbook",
  "description": "New stills from the studio session.",
  "platformAccountIds": ["acct_01"],
  "media": [{ "assetId": 88421, "kind": "image" }]
}
```

The result's `data.taskIds` may hold more than one id. Run step 3 for each id
you intend to send.

## 3. Submit the draft

Publish now, `publish_publishing_task`:

```json
{
  "organizationId": "1001",
  "taskId": "<id from taskIds>",
  "mode": "publish_now"
}
```

Schedule instead, with an offset-aware `scheduledTime` between 2 hours and
14 days from now:

```json
{
  "organizationId": "1001",
  "taskId": "<id from taskIds>",
  "mode": "schedule",
  "scheduledTime": "2026-09-21T09:00:00+08:00",
  "timezone": "Asia/Shanghai"
}
```

## Local platforms

When any account is Xiaohongshu (`xhs`), Douyin, or Kuaishou, call
`list_desktop_instances` first and pass its `installationId` as
`desktopInstanceId`: on the create call when `mode` is `schedule` or
`publish_now`, or on the submit call when a draft leaves draft.

```json
{
  "organizationId": "1001",
  "taskId": "<id from taskIds>",
  "mode": "publish_now",
  "desktopInstanceId": "<installationId from list_desktop_instances>"
}
```

Cloud platforms (TikTok, YouTube, Facebook, Instagram, X, LinkedIn) take no
`desktopInstanceId`.

## Skip the draft

A `schedule` or `publish_now` create is submitted in the same call. The body is
step 2 with `mode` changed, `scheduledTime` added for `schedule`, and
`desktopInstanceId` added for a local task.
