# tally

A tiny CSV ledger.

```bash
uv sync
uv run python -m tally report examples/household.csv
```

## Commands

| Command | Description |
|---|---|
| `report FILE` | Print totals per category |
| `add FILE --date D --amount A --category C [--tag T] [--memo M]` | Append an entry |

See [docs/SPEC.md](docs/SPEC.md) for the file format.
