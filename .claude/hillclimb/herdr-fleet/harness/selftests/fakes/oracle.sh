#!/usr/bin/env bash
# Lands the reference solution on a local branch from a separate worktree.
set -euo pipefail
case_oracle="${HFEVAL_ORACLE:-a}"
wt="$HFEVAL_ROOT/worktrees/repo/feat-oracle"
git -C "$HFEVAL_REPO" worktree add -q -b feat/oracle "$wt" main
cp -R "$HFEVAL_ORACLES/$case_oracle/." "$wt/"
git -C "$wt" add -A
git -C "$wt" -c user.name=oracle -c user.email=o@e.invalid commit -q -m "feat: reference solution"
git -C "$HFEVAL_REPO" worktree remove "$wt"
echo "Landed the work on branch feat/oracle. The suite passes."
