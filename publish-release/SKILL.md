---
name: publish-release
description: |
  The release convention for this user's projects: unreleased work
  accumulates under CHANGELOG's [Unreleased] heading, and a single
  `make publish [VERSION]` cuts it. Use when asked to release, cut a
  version, publish, tag, "发布" / "出一个 release" / "推 tag", or when
  setting up / fixing a project's release pipeline. Also use before
  writing any bespoke version-bump script — this is the standard that
  script must implement.
---

# Publish Release

One command cuts a release: `make publish [VERSION]`.

Everything else — where notes live, how versions propagate, which
files are hand-edited and which are regenerated — follows from that.

## The convention

**Unreleased work lives under `## [Unreleased]` in `CHANGELOG.md`.**
Every change lands there as it is merged, not at release time. Cutting
a release is then a mechanical rename, not an archaeology exercise over
`git log`.

```markdown
## [Unreleased]

### Added
- ...

## [1.4.2] - 2026-08-02
```

If `[Unreleased]` is empty at publish time, **there is nothing to
release** — abort and say so. Do not synthesize notes from commits;
that is a signal the convention was not followed, and papering over it
hides the gap.

## The `make publish` contract

```bash
make publish            # patch bump: 1.4.2 -> 1.4.3
make publish 2.0.0      # explicit version
make publish --dry-run  # print the plan, change nothing
```

### Version resolution

1. An explicit argument wins. Strip a leading `v`. Reject anything that
   is not `X.Y.Z`.
2. Otherwise take the newest released `## [X.Y.Z]` heading in
   `CHANGELOG.md` and increment the patch segment.
3. Cross-check that heading against the newest `vX.Y.Z` git tag. If they
   disagree, **abort** — one of them is lying and guessing which is how
   a release gets cut from the wrong base.

### What it does, in order

1. **Preflight.** Clean tree; on the default branch; `[Unreleased]` is
   non-empty; the target tag does not already exist locally or on the
   remote; required tooling present (`gh`, and whatever the chosen mode
   needs).
2. **Cut the CHANGELOG.** Rename `## [Unreleased]` to
   `## [X.Y.Z] - YYYY-MM-DD`, insert a fresh empty `## [Unreleased]`
   above it, and add the link-reference line if the file uses them.
3. **Propagate the version** into the project's version files (below).
4. **Regenerate lockfiles by command** (below).
5. **Commit** as `chore: release vX.Y.Z`.
6. **Push** the commit, then create and push the annotated tag `vX.Y.Z`.
7. **Release**, by whichever mode the project uses (below).

Steps 5–7 mutate shared state. See *Plan and confirm*.

## Version propagation

Hand-edit only the file that *declares* the version. Never hand-edit a
generated file.

| Ecosystem | File | Field |
|---|---|---|
| Node | `package.json` | `version` |
| Rust | `Cargo.toml` (workspace root) | `[workspace.package] version`, or `[package] version` in a single crate |
| Tauri | `src-tauri/tauri.conf.json` | `version` |
| Swift / Xcode | `*.xcconfig` or the target's `MARKETING_VERSION` | — |
| Python | `pyproject.toml` | `[project] version` |
| Flutter | `pubspec.yaml` | `version` |
| Go | none | tags are the version |

**Detect, do not assume.** Glob for these files rather than trusting a
template — a repo can be several of these at once, and a monorepo can
have many `package.json` files.

### Two rules that are easy to get wrong

**`"private": true` means no version to manage.** A private
`package.json` is never published to a registry, and its `version` field
is decoration. Leave it alone. Same for any workspace-root manifest that
exists only to hold workspaces.

**Crate and package versions that are inherited stay inherited.** In a
Cargo workspace, members using `version.workspace = true` need no edit.
Editing them is not merely redundant, it breaks the inheritance the
workspace exists to provide.

## Lockfiles

Lockfiles record the version too. **Regenerate them with the tool that
owns them; never edit a lockfile by hand.** A hand-edited lockfile is
indistinguishable from a corrupt one and will be silently overwritten by
the next install.

Pick the command from the lockfile that is actually present, not from
what the README says the project uses:

| Lockfile | Command |
|---|---|
| `Cargo.lock` | `cargo update --workspace` |
| `pnpm-lock.yaml` | `pnpm install --lockfile-only` |
| `package-lock.json` | `npm install --package-lock-only` |
| `yarn.lock` | `yarn install --mode update-lockfile` |
| `bun.lockb` / `bun.lock` | `bun install` |
| `uv.lock` | `uv lock` |
| `poetry.lock` | `poetry lock --no-update` |

If a repo has more than one JS lockfile, that is a bug worth reporting
before releasing — the second one is stale and someone is installing
from it.

## Publish modes

A project uses exactly one. Decide once, record it in the repo's own
release docs, and make `make publish` implement it.

### Mode 1 — GitHub Actions (tag-triggered)

`make publish` pushes the tag and stops. A workflow triggered by
`push: tags: ['v*']` builds the artifacts and creates the GitHub
release, taking the body from the CHANGELOG section for that tag.

Use this when the build is reproducible on a runner. It is the better
default: the artifact provenance is a public log rather than someone's
laptop.

The workflow **must** extract release notes from `CHANGELOG.md` for the
tag it was triggered by, not from commit messages. See
[`references/release.yml`](references/release.yml).

### Mode 2 — Local build

`make publish` builds and signs locally, then creates the tag, pushes
it, and runs `gh release create` with the artifacts and the CHANGELOG
section as the body.

Use this when the build needs local secrets, hardware, or notarization
that cannot run on a runner — Apple codesigning and notarization being
the usual reason.

In both modes the tag is annotated (`git tag -a`), never lightweight,
and the release notes come from the CHANGELOG section.

## Plan and confirm

**Before mutating anything, print the whole plan and ask.** Not a yes/no
on an opaque "publish?" — the actual steps, resolved:

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

`--dry-run` prints exactly this and exits 0 without touching anything.
`--yes` skips the prompt, for CI only.

The plan is the point. Most bad releases are not caused by a broken
script; they are caused by a correct script pointed at the wrong
version, the wrong branch, or an empty changelog.

## Setting this up in a repo

1. Read what the repo already does. If there is an existing release
   script, this convention replaces it — do not leave two paths.
2. Detect the ecosystems present and write the version-file and
   lockfile lists into the script explicitly. A script that globs at
   runtime is harder to review than one that names its files.
3. Choose the publish mode and say why in a comment.
4. Add `publish` to the `Makefile`, forwarding arguments.
5. Verify with `make publish --dry-run` **before** the first real run,
   and check that the printed version, branch, and notes are what you
   expect.
6. Write the release procedure into the repo's own docs. This skill is
   the standard; the repo documents its instance of it.

## Failure modes to guard against

- **Cutting from a stale base.** The tag/CHANGELOG cross-check in
  version resolution exists for this.
- **A tag that already exists.** Check locally *and* on the remote.
  A local check alone passes right up until the push fails, after the
  commit has already landed.
- **Pushing the tag before the commit.** The tag must point at a commit
  that reviewers can fetch. Push the branch first.
- **A release with empty notes.** If the CHANGELOG section extracts to
  nothing, abort rather than publishing a blank release.
- **Partial failure.** If the tag pushed but the release creation
  failed, say so precisely and tell the user the tag exists — the
  recovery is `gh release create` against the existing tag, not a
  re-run of the whole flow.
