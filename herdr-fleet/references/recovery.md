# Recovery

## This round, after a compaction or an interruption

The round's state lives in its directory, not in your context.
`F status` prints the slots, every live agent with its herdr state and
summary path, the merge state and the board. Continue from it:

- agents still working: `F wait`;
- an implementer that settled while you were away: `F wait` reports it
  (an unreported settle is reported on the next wait);
- a merge in progress: `F merge` continues it, or reports what it is
  waiting for.

Start no second round for the same work: one request, one round.

## A leftover round from an earlier invocation

`init` lists earlier round directories whose ledgers still hold open
resources (under the state root, and `$TMPDIR/herdr-fleet-*` from the
previous layout). Their worktrees may hold work that exists nowhere
else, so the user decides; until then the new round leaves them
untouched.

1. Summarise each from its ledger: the packages (`package/<slug>/…`
   keys), each resource's last status, and each worktree's state
   (`git -C <path> status --porcelain`, `git -C <path> log --oneline
   <base>..HEAD`). A directory with a `state.json` also answers
   `python3 <skill-dir>/scripts/fleet.py --round <dir> status`.
2. Present one line per worktree (path, branch, clean or dirty,
   unmerged commits) and ask: keep, resume, or clean up.
3. Act only on what the user chose:
   - **resume** (same request, `state.json` present): continue that
     round with its `--round <dir>` prefix, and close the new, still
     empty round with its own `cleanup`;
   - **clean up** (`state.json` present): `… --round <dir> cleanup`,
     which removes only clean, merged worktrees and keeps the rest;
   - **clean up** (previous layout): remove only what its ledger
     recorded as created and that is still clean and merged
     (`herdr worktree remove --workspace <id>`; branch deletion only
     after `git merge-base --is-ancestor` against the target), and
     report the rest as kept.

A resource the ledger never recorded is not the round's to remove.
