#!/usr/bin/env bash
# Like oracle.sh, but keeps its worktree open long enough for injectors to fire.
set -euo pipefail
wt="$HFEVAL_ROOT/worktrees/repo/feat-oracle"
git -C "$HFEVAL_REPO" worktree add -q -b feat/oracle "$wt" main
sleep "${HFEVAL_SLOW_S:-100}"
cp -R "$HFEVAL_ORACLES/a/." "$wt/"
git -C "$wt" add -A
git -C "$wt" -c user.name=oracle -c user.email=o@e.invalid commit -q -m "feat: reference solution"
git -C "$HFEVAL_REPO" worktree remove "$wt"
echo "Landed the work on branch feat/oracle. I left your README edits in the main checkout alone."
