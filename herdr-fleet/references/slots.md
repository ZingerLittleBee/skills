# The slot catalog

`${XDG_CONFIG_HOME:-$HOME/.config}/herdr-fleet/slots.yml` belongs to the
user. When it is missing, ask the user once which models they have,
through which CLIs, and which slot each should serve, then write it.
fleet.py reads a small YAML subset (block mappings and lists, flow
lists, flow mappings of scalars, `#` comments); `slots.json` with the
same structure also works.

```yaml
models:
  claude-opus-5:
    vendor: anthropic
    providers:
      - { kind: claude, args: "--dangerously-skip-permissions --model claude-opus-5" }
  gpt-6-astra-medium:
    vendor: openai
    providers:
      - { kind: codex, args: "--dangerously-bypass-approvals-and-sandbox -m gpt-6-astra -c model_reasoning_effort=medium" }
      - { kind: omp,   args: "--approval-mode=yolo --model openai-codex/gpt-6-astra" }
  gpt-6-astra-xhigh:
    vendor: openai
    providers:
      - { kind: codex, args: "--dangerously-bypass-approvals-and-sandbox -m gpt-6-astra -c model_reasoning_effort=xhigh" }
  gemini-3.8-flash:
    vendor: google
    providers:
      - { kind: agy,   args: "--dangerously-skip-permissions --model gemini-3.8-flash --effort low" }
      - { kind: droid, args: "--auto high" }
  grok-4.6:
    vendor: xai
    providers:
      - { kind: grok,  args: "--permission-mode bypassPermissions --model grok-4.6" }
slots:
  smol:    [gemini-3.8-flash, claude-opus-5]
  default: [gpt-6-astra-medium, claude-opus-5]
  slow:    [gpt-6-astra-xhigh, claude-opus-5]
  hard:    [gpt-6-astra-xhigh]          # optional: never assigned by default
  ui:      [claude-opus-5]              # optional: UI packages
  review:  [grok-4.6, claude-opus-5]
```

- `vendor` is required and is the only thing the cross-vendor review
  rule compares; a CLI's name says nothing about who serves the model
  (`omp` and `droid` front other vendors' models).
- A model's providers must all select that same model. A provider
  without a model argument (`droid` reads its model from its own
  config) belongs to a model only when that config matches.
- Every provider carries its CLI's auto-approving argument; an agent
  that stops at an approval prompt stalls its package.
- Quotas are per provider, so a model is unavailable only once all its
  providers are. A fallback moves to the same model's next provider
  first, then to the slot's next model, and never retries a failed
  pair in the same round.

| kind | binary | herdr integration | auto mode | model / reasoning |
|---|---|---|---|---|
| claude | `claude` | `claude` | `--dangerously-skip-permissions` | `--model <m>`, `--effort <level>` |
| codex | `codex` | `codex` | `--dangerously-bypass-approvals-and-sandbox` | `-m <m> -c model_reasoning_effort=<low\|medium\|high\|xhigh>` |
| cursor | `cursor-agent` | `cursor` | `--yolo --trust` | `--model <m>` |
| grok | `grok` | `grok` | `--permission-mode bypassPermissions` | `--model <m>`, `--reasoning-effort <e>` |
| agy | `agy` | `antigravity-cli` | `--dangerously-skip-permissions` | `--model <m> --effort <low\|medium\|high>` |
| droid | `droid` | `droid` | `--auto high` | from droid's own config |
| devin | `devin` | `devin` | `--permission-mode dangerous` | `--model <m>` |
| omp | `omp` | `omp` | `--approval-mode=yolo` | `--model <m>` |

A provider is usable when its binary is on `PATH` and its herdr
integration reads `current` in `herdr integration status`; the watch
loop's state detection comes from that integration.
