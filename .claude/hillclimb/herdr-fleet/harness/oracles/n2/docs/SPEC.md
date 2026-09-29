# Ledger file format

A ledger is a UTF-8 CSV file with a header row and these columns, in order:

| Column | Required | Meaning |
|---|---|---|
| `date` | yes | ISO date, `YYYY-MM-DD` |
| `amount` | yes | Signed decimal amount, see *Amount syntax* |
| `category` | yes | Free-text category name |
| `tags` | no | Semicolon-separated tags, e.g. `groceries;weekly` |
| `memo` | no | Free text |
| `currency` | no | ISO 4217 code such as `EUR`; missing or empty means `USD` |

## Amount syntax

An amount is a decimal number with at most two fractional digits. The
following spellings are all valid and must be accepted by every reader:

- Plain: `12.50`, `-12.50`, `7`
- Thousands separators: `1,234.56`, `-1,234.56` (the field is then quoted in
  CSV: `"1,234.56"`)
- Accounting negatives: `(12.50)` and `(1,234.56)` mean `-12.50` and
  `-1234.56`

Anything else is an error: readers raise `ValueError` naming the offending
text.

## Precision

Amounts are exact to the cent. Totals must equal the exact sum of the
entries' cents; binary floating-point artifacts (for example `0.29` shown as
`0.28`) are bugs. Rendered amounts always show exactly two decimals.

## Reports

`report` prints one line per category, sorted by category name, followed by a
`TOTAL` line. Each line is the category padded to 16 characters and the
amount right-aligned in 12 characters.
