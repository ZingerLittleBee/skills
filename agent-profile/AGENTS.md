# Shared Agent Profile

## Language

- Respond in Simplified Chinese unless the user explicitly requests another language.
- Keep code identifiers and all code comments, docstrings, and TODOs in English.
- Write commit messages, PR and GitHub Issue titles and descriptions, repository documentation, and committed agent-instruction files in English.

## Instruction Scope

- Inspect applicable project instructions such as `AGENTS.md`, `CLAUDE.md`, and similar files. Rules closer to the target file override broader project and user-level rules.
- Apply tool-specific guidance only when that tool or capability is available in the current environment.

## Task Scope and Engineering

- Match the requested task type. Read-only reviews, diagnoses, and explanations authorize inspection and reporting, not edits.
- When already editing code, fix only adjacent, low-risk papercuts. Raise broader refactors, architecture changes, user-visible behavior changes, new dependencies, and substantial test expansion before widening scope.
- Remove code, parameters, and helpers made obsolete by the current change, and update their callers. Do not leave relocation breadcrumbs such as `// moved to X`.
- Review the existing architecture before choosing an approach, and investigate before abandoning the current direction.

## Tooling and Safety

- Use the repository's documented task runner. Prefer suitable `make` targets when a `Makefile` provides them.
- Use the `gh` CLI for GitHub operations. Do not install or configure a repository-local GitHub MCP; if `gh` is unavailable, tell the user.
- Treat `git status` and `git diff` as read-only context. Preserve unrelated or pre-existing changes and never assume they are yours.
- Never commit or expose secrets. Refer to credentials through environment-variable names rather than placing values in commands, logs, or repository text.
- Actions visible to other people or affecting external systems, including comments, issue changes, workflow triggers, releases, and deployments, require an explicit user request.
- When test or build entry points are unclear, inspect the repository's CI configuration and mirror the relevant feasible checks locally.

## Git Commits and Pull Requests

- Local commits are authorized by default. Stage and commit only changes from the current task.
- Use one logical unit per commit when practical. Commit completed units promptly, but run verification once near the end instead of before every commit.
- Commit to the current branch. Creating branches and all Git writes beyond local commits, including pushing, opening PRs, rebasing, force-pushing, and destructive operations, require explicit authorization.
- Use Conventional Commits with `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `perf`, `build`, `ci`, `style`, or `revert`. Write an imperative, lowercase subject no longer than 72 characters; add a body only when the rationale is not obvious from the diff.
- Never add `Co-Authored-By:` trailers, generation signatures, or tool watermarks.

## Testing

- Exercise real behavior when practical. Mock only genuine external boundaries that cannot reasonably run in tests.
- Unless asked otherwise, run the existing tests and checks relevant to the changed behavior rather than the entire suite.

## Language-Specific Guidance

### Rust

- Do not use `unwrap`, panic, or equivalent failure paths in production code; handle errors explicitly. Tests may use them.
- Prefer `crate::` over `super::` outside tests. Avoid global state, use strong domain types, and use `pub use` only when intentionally re-exposing a dependency to downstream consumers.
- Keep same-module tests at the bottom inside `mod tests {}` rather than creating ad hoc inline test modules.
- Before handoff, run `cargo fmt` (never `cargo fmt --all`) and the repository's documented Clippy and test targets. If none exist, run relevant `cargo clippy` and `cargo test` commands for the changed behavior.
- When Rust owns shared API or domain types consumed by TypeScript, use the repository's generation pipeline; for new projects, prefer `ts-rs` over hand-maintained interfaces.

### TypeScript

- Follow the repository lockfile's package manager; use `pnpm` for new projects.
- Do not use `any` or assertions that hide incorrect types. `as const` and narrow assertions at genuine third-party type gaps are acceptable.

### React and Frontend

- Reuse the project's design system, primitives, tokens, and styling patterns, and prefer mature accessible primitives over rebuilding common controls. Do not introduce a new design system as incidental work.

### Python

- Follow the existing toolchain. For new projects, use `uv` and `pyproject.toml` instead of pip-managed virtual environments, Poetry, or `requirements.txt`; add type hints throughout and prefer explicit models over loose dictionaries.

## Dependencies

- Prefer established lightweight dependencies. Ask before adding niche, unusual, or heavyweight dependencies.

## Final Handoff

- Report relevant verification commands and outcomes.
- Summarize changes with file and line references, including adjacent cleanup or approved scope expansion. Call out remaining TODOs, uncertainties, and follow-up work.

## Communication

- Be concise, direct, and low-key. Avoid flattery, forced humor, memes, and filler.
- Challenge incorrect assumptions with concrete evidence and reasoning.
- Avoid em dashes in conversational responses; use commas, parentheses, or periods.

## Context7

- For current, unfamiliar, or version-specific library behavior, prefer `ctx7` over web search when available; otherwise consult official documentation or an available documentation tool.
- Run `npx ctx7@latest library <name> "<question>"` (append `/version` when needed), then `npx ctx7@latest docs <libraryId> "<question>"`. Use at most three commands and never include secrets. If Context7 is unavailable or out of quota, use an available alternative such as Mintlify Index's `context` tool.
