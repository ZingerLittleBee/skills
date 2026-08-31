# Reach a Perfect React Doctor Score

## Objective

Run `npx react-doctor@latest` and properly fix every reported issue until React Doctor produces a verified score of 100.

## Before starting

1. Read and follow the repository and target-directory instructions, including `AGENTS.md` and `CLAUDE.md`.
2. Inspect the current Git status and preserve unrelated user changes.
3. Inspect the project's package manager, scripts, framework configuration, and existing test setup before making changes.
4. Run `npx react-doctor@latest` once to capture the baseline score and findings.

## Requirements

- Fix the root cause of every React Doctor finding.
- Keep changes focused, idiomatic, maintainable, and consistent with the existing architecture and design system.
- Reuse existing components, utilities, and project conventions instead of creating parallel abstractions.
- Remove code or helpers made obsolete by the fixes and update their callers.
- Rerun React Doctor after each coherent group of fixes and use the new findings to guide the next iteration.
- Run the existing tests, type checks, lint checks, and build checks relevant to the changed behavior.
- Exercise real application behavior when practical, especially when a fix affects rendering, state, navigation, forms, or interaction.

## No shortcuts

- Do not disable, suppress, ignore, or exclude React Doctor checks or findings.
- Do not weaken TypeScript types, lint rules, tests, build checks, accessibility behavior, or runtime validation.
- Do not delete working features or user-visible behavior merely to remove a finding.
- Do not replace correct architecture with score-specific hacks or dead code.
- Do not modify generated output, dependency internals, or tool caches to manipulate the score.
- Do not claim success from partial output, stale output, a different command, or an inferred score.
- Do not add or upgrade dependencies unless the fix genuinely requires it and repository instructions permit it.

## Completion criteria

- A fresh, successful run of `npx react-doctor@latest` reports a score of exactly 100.
- Relevant tests, type checks, lint checks, and build checks pass after the final fixes.
- The final report includes the baseline score, final score, issues fixed, files changed, verification commands, and any remaining uncertainty.

Do not mark the goal complete until the exact score of 100 is observed in fresh command output. If an external or tooling failure prevents completion, record the exact blocker and evidence instead of claiming success.
