# Authoring a repo's `make publish`

Reached from `SKILL.md` when wiring this convention into a repo, or
when you need the declared/derived file for a specific ecosystem.

## Declared files

Hand-edit exactly these. Glob for them rather than trusting a template
— a repo can be several ecosystems at once, and a monorepo can hold
many `package.json` files, most of them `"private": true`.

| Ecosystem | File | Field |
|---|---|---|
| Node | `package.json` | `version` |
| Rust | `Cargo.toml` (workspace root) | `[workspace.package] version`, or `[package] version` in a single crate |
| Tauri | `src-tauri/tauri.conf.json` | `version` |
| Swift / Xcode | `*.xcconfig` or the target's `MARKETING_VERSION` | — |
| Python | `pyproject.toml` | `[project] version` |
| Flutter | `pubspec.yaml` | `version` |
| Go | none | tags are the version |

An Apple `Info.plist` that the packaging script *generates* from a
version variable is derived, not declared — find the variable.

## Derived files

Regenerate with the tool that owns them. A hand-edited lockfile is
indistinguishable from a corrupt one and the next install overwrites it
anyway.

Pick the command from the lockfile actually present in the repo, not
from what the README says the project uses:

| Lockfile | Command |
|---|---|
| `Cargo.lock` | `cargo update --workspace` |
| `pnpm-lock.yaml` | `pnpm install --lockfile-only` |
| `package-lock.json` | `npm install --package-lock-only` |
| `yarn.lock` | `yarn install --mode update-lockfile` |
| `bun.lockb` / `bun.lock` | `bun install` |
| `uv.lock` | `uv lock` |
| `poetry.lock` | `poetry lock --no-update` |

More than one JS lockfile is a bug worth reporting before releasing:
the second one is stale and someone is installing from it.

## Publish modes

A repo uses exactly one. Decide once, record it in the repo's own
release docs, and make `make publish` implement it.

### Mode 1 — GitHub Actions (tag-triggered)

`make publish` pushes the tag and stops. A workflow triggered by
`push: tags: ['v*']` builds the artifacts and creates the GitHub
release, taking the body from the CHANGELOG section for that tag.

The better default, for builds that run on a runner: artifact
provenance is a public log. The workflow takes its notes from
`CHANGELOG.md` for the tag it was triggered by — see
[`release.yml`](release.yml), whose notes step is meant to be copied
as-is.

### Mode 2 — Local build

`make publish` builds and signs locally, then creates the tag, pushes
it, and runs `gh release create` with the artifacts and the CHANGELOG
section as the body.

For builds needing local secrets, hardware, or notarization that cannot
run on a runner — Apple codesigning and notarization being the usual
reason.

Both modes use an annotated tag (`git tag -a`).

## Wiring it up

1. Read what the repo already does. An existing release script is
   replaced by this one, so that the repo has a single path.
2. Detect the ecosystems present and write the declared and derived
   file lists into the script explicitly. A script that names its files
   is easier to review than one that globs at runtime.
3. Choose the publish mode and say why in a comment.
4. Add `publish` to the `Makefile`, forwarding arguments.
5. Run `make publish --dry-run` before the first real run, and confirm
   the printed version, branch, and notes are what you expect.
6. Write the release procedure into the repo's own docs. This skill is
   the standard; the repo documents its instance of it.
