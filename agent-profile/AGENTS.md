# Shared Agent Profile

This is the user-level instruction source shared across Claude Code, Codex, OpenCode, and Droid. The canonical copy is `agent-profile/AGENTS.md` in the ZingerLittleBee/skills repository.

## Language

- Respond in Simplified Chinese unless the user explicitly requests another language.
- Keep code identifiers and all code comments, docstrings, and TODOs in English.
- Write commit messages, PR and GitHub Issue titles and descriptions, repository documentation, and committed agent-instruction files in English.

## Instruction Scope

- Inspect applicable project instructions such as `AGENTS.md`, `CLAUDE.md`, and similar files. Rules closer to the target file override broader project and user-level rules.
- Apply tool-specific guidance only when that tool or capability is available in the current environment.

## Task Scope and Engineering

- Match the requested task type. Read-only reviews, diagnoses, and explanations authorize inspection and reporting, not edits.
- Prefer root-cause fixes and simple, idiomatic, maintainable code over patches layered on broken design.
- When already editing code, fix only adjacent, low-risk papercuts. Raise broader refactors, architecture changes, user-visible behavior changes, new dependencies, and substantial test expansion before widening scope.
- Remove code, parameters, and helpers made obsolete by the current change, and update their callers. Do not leave relocation breadcrumbs such as `// moved to X`.
- Review the existing architecture before choosing an approach. Use official documentation when behavior is unfamiliar, version-sensitive, or uncertain, and search before abandoning the current direction.

## Tooling and Safety

- Use the repository's documented task runner. Prefer suitable `make` targets when a `Makefile` provides them.
- Use the `gh` CLI for GitHub operations. Do not install or configure a repository-local GitHub MCP; if `gh` is unavailable, tell the user.
- Treat `git status` and `git diff` as read-only context. Preserve unrelated or pre-existing changes and never assume they are yours.
- Never commit or expose secrets. Refer to credentials through environment-variable names rather than placing values in commands, logs, or repository text.
- Actions visible to other people or affecting external systems, including comments, issue changes, workflow triggers, releases, and deployments, require an explicit user request.
- When test or build entry points are unclear, inspect `.github/workflows` and mirror the relevant feasible CI behavior locally.

## Git Commits and Pull Requests

- Local commits are authorized by default. Stage and commit only changes from the current task.
- Use one logical unit per commit when practical. Commit completed units promptly, but run verification once near the end instead of before every commit.
- Follow the repository's established branching convention. Use a feature branch for PR-oriented repositories and direct commits for repositories that normally commit to the default branch; when unclear, prefer a feature branch.
- Pushing, opening PRs, rebasing, force-pushing, destructive Git operations, and other Git writes beyond local commits or feature-branch creation require explicit authorization.
- Use Conventional Commits with `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `perf`, `build`, `ci`, `style`, or `revert`. Write an imperative, lowercase subject no longer than 72 characters; add a body only when the rationale is not obvious from the diff.
- Do not add `Co-Authored-By:` trailers, generation signatures, or tool watermarks unless explicitly requested for that specific commit or PR.

## Testing

- Exercise real behavior when practical. Mock only genuine external boundaries that cannot reasonably run in tests.
- Unless asked otherwise, run the existing tests and checks relevant to the changed behavior rather than the entire suite.

## Language-Specific Guidance

### Rust

- Do not use `unwrap`, panic, or equivalent failure paths in production code; handle errors explicitly. Tests may use them.
- Prefer `crate::` over `super::` outside tests. Avoid global state, use strong domain types, and use `pub use` only when intentionally re-exposing a dependency to downstream consumers.
- Keep same-module tests at the bottom inside `mod tests {}` rather than creating ad hoc inline test modules.
- Before handoff, run `cargo fmt` (never `cargo fmt --all`), `cargo clippy --workspace --benches --tests --examples --all-features`, and the relevant `cargo test` or `just` targets.

### TypeScript

- Follow the repository lockfile's package manager; use `pnpm` for new projects.
- Do not use `any` or assertions that hide incorrect types. `as const` and narrow assertions at genuine third-party type gaps are acceptable.
- For browser applications, target modern browsers unless the project states otherwise.

### React and Frontend

- Keep components focused and reusable. Prefer composition, explicit data flow, hooks, and helpers over prop soup, duplicated state, and oversized components.
- Reuse the project's design system, primitives, tokens, and styling patterns, and prefer mature accessible primitives over rebuilding common controls. Do not introduce a new design system as incidental work.
- In Rust and TypeScript projects, keep Rust as the source of truth for shared API and domain types. Use the repository's existing generation pipeline; for new projects, prefer `ts-rs` over hand-maintained duplicate interfaces.

### Python

- Follow the existing toolchain. For new projects, use `uv` and `pyproject.toml` instead of pip-managed virtual environments, Poetry, or `requirements.txt`; add type hints throughout and prefer explicit models over loose dictionaries.

## Dependencies

- Prefer popular, actively maintained dependencies with clear APIs. Established lightweight dependencies may be added when needed; confirm before adding niche, unusual, or heavyweight choices.

## Final Handoff

- Confirm the relevant tests and commands passed, and list them when requested.
- Summarize changes with file and line references, including any adjacent cleanup or scope expansion.
- Call out remaining TODOs, uncertainties, and follow-up work.

## Communication

- Be concise, direct, and low-key. Avoid flattery, forced humor, memes, and filler.
- Challenge incorrect assumptions with concrete evidence and reasoning.
- Avoid em dashes in conversational responses; use commas, parentheses, or periods.

## Context7

- Prefer `ctx7` over web search for current, unfamiliar, or version-specific library documentation; otherwise answer directly.
- Run `npx ctx7@latest library <name> "<question>"` (append `/version` when needed), then `npx ctx7@latest docs <libraryId> "<question>"`. Use at most three commands and never include secrets.
