---
name: publish-release
description: |
  Release convention: cut CHANGELOG's [Unreleased] with
  `make publish`. Use when asked to publish a release
  ("发布"), when setting up or fixing a repo's release pipeline, or
  before writing any bespoke version-bump script — this is the
  standard that script must implement.
---

# Publish Release

One command cuts a release: `make publish`.

`CHANGELOG.md` is the source. It holds both the version being cut and
the notes that ship with it; everything else is derived from it.

## The convention

**Unreleased work lives under `## [Unreleased]`.** Every change lands
there as it is merged, so cutting a release is a mechanical rename
rather than an archaeology exercise over `git log`.

```markdown
## [Unreleased]

### Added
- ...

## [1.4.2] - 2026-08-02
```

An empty `[Unreleased]` means **there is nothing to release** — abort
and say so. The convention was not followed, that gap is the finding,
and synthesizing notes from commits buries it.

The release notes are the `## [X.Y.Z]` section verbatim, wherever notes
are needed: the GitHub release body, the plan preview, the workflow.

## Declared and derived

One file *declares* the version. Every other place it appears is
derived, and belongs to the tool that produced it:

- **Declared** — hand-edit exactly one file per ecosystem
  (`package.json`, `Cargo.toml`, `tauri.conf.json`, …).
- **Derived** — lockfiles and generated bundle manifests. Regenerate
  each with the command that owns it.
- **No declaration** — a `package.json` marked `"private": true` is
  never published, so its `version` field declares nothing; a Cargo
  member with `version.workspace = true` declares upstream; a Go module
  declares in its tags. These stay as they are.

Which file is which, per ecosystem, and the regeneration command per
lockfile: [`references/authoring.md`](references/authoring.md).

## The `make publish` contract

```bash
make publish                  # patch bump: 1.4.2 -> 1.4.3
make publish VERSION=2.0.0    # explicit version
make publish DRY_RUN=1        # print the plan, change nothing
make publish YES=1            # skip the confirmation prompt
```

Options are make variables, not flags, because flags cannot reach the
recipe: make consumes `--dry-run` as its own `-n` (printing the recipe
instead of running it) and rejects unknown long options outright.

### Version resolution

1. An explicit `VERSION=` wins. Strip a leading `v`. Reject anything
   that is not `X.Y.Z` — prereleases like `1.0.0-rc.1` are out of
   scope for this convention.
2. Otherwise take the newest released `## [X.Y.Z]` heading in
   `CHANGELOG.md` and increment the patch segment.
3. Cross-check that heading against the newest `vX.Y.Z` git tag. If
   they disagree, **abort** — one of them is lying, and guessing which
   is how a release gets cut from the wrong base.

### What it does, in order

1. **Preflight.** Clean tree; on the default branch; `[Unreleased]`
   non-empty; the target tag absent locally *and* on the remote (a
   local-only check passes right up until the push fails, by which time
   the commit has landed); required tooling present.
2. **Cut the CHANGELOG.** Rename `## [Unreleased]` to
   `## [X.Y.Z] - YYYY-MM-DD`, insert a fresh empty `## [Unreleased]`
   above it, and add the link-reference line if the file uses them.
3. **Update the declared version** in each version file.
4. **Regenerate the derived files** by command.
5. **Commit** as `chore: release vX.Y.Z`.
6. **Push the commit, then create and push the annotated tag** `vX.Y.Z`.
   In that order: the tag has to point at a commit reviewers can fetch.
7. **Release**, by whichever mode the repo uses.
8. **Verify.** `gh release view vX.Y.Z` shows a non-draft release whose
   body is the CHANGELOG section and whose assets are all present.
   Under Mode 1 that means waiting for the workflow to finish; a pushed
   tag is not a published release.

Steps 5–7 mutate shared state. See *Plan and confirm*.

If a step after the tag push fails, report that precisely and name the
tag: recovery is `gh release create` against the existing tag, not a
re-run of the whole flow.

## Plan and confirm

**Before mutating anything, print the whole plan and ask.** Not a
yes/no on an opaque "publish?" — the actual steps, resolved:

```
Publish v2.1.0  (patch bump from 2.0.2)

  CHANGELOG.md    [Unreleased] -> [2.1.0] - 2026-08-02, new empty [Unreleased]
  package.json    2.0.2 -> 2.1.0
  Cargo.toml      2.0.2 -> 2.1.0  ([workspace.package])
  pnpm-lock.yaml  regenerate via `pnpm install --lockfile-only`
  Cargo.lock      regenerate via `cargo update --workspace`

  commit          chore: release v2.1.0
  push            origin main
  tag             v2.1.0 (annotated) -> origin
  release         GitHub Actions (.github/workflows/release.yml)

Release notes (from CHANGELOG [Unreleased]):
  ### Added
  - ...

Proceed? [y/N]
```

`DRY_RUN=1` prints exactly this and exits 0 without touching anything.
`YES=1` skips the prompt, for a non-interactive run of a plan already
reviewed with `DRY_RUN=1`.

## Setting this up in a repo

Choosing a publish mode, listing a repo's declared and derived files,
and wiring `make publish` into a repo that does not have it:
[`references/authoring.md`](references/authoring.md).
