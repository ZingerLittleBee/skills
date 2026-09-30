# tally

A tiny CSV ledger.

```bash
uv sync
uv run python -m tally report examples/household.csv
```

## Commands

| Command | Description |
|---|---|
| `report FILE [--only CATEGORY]` | Print totals per category |
| `add FILE --date D --amount A --category C [--tag T] [--memo M]` | Append an entry |
| `stats FILE` | Print the entry count and the largest and smallest amounts |
| `find FILE TEXT` | Print entries whose memo contains TEXT |

See [docs/SPEC.md](docs/SPEC.md) for the file format.
