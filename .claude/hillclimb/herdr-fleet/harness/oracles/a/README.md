# tally

A tiny CSV ledger.

```bash
uv sync
uv run python -m tally report examples/household.csv
```

## Commands

| Command | Description |
|---|---|
| `report FILE [--format text\|json]` | Print totals per category |
| `add FILE --date D --amount A --category C [--tag T] [--memo M]` | Append an entry |
| `tags FILE` | Count entries per tag |
| `months FILE` | Print totals per calendar month |

See [docs/SPEC.md](docs/SPEC.md) for the file format.
