# tally

Tiny CSV ledger CLI (`python -m tally`). Read `docs/SPEC.md` before changing
parsing or reporting behavior.

## Commands

- Install dependencies: `uv sync`
- Run the whole test suite: `uv run pytest -q`
- Run one test file: `uv run pytest -q tests/test_report.py`

## Conventions

- Standard library only at runtime; pytest is the only dev dependency.
- Every behavior change comes with tests under `tests/`.
- Conventional Commits, imperative lowercase subject under 72 characters.
- Keep `README.md`'s command table in sync with `tally/cli.py`.
