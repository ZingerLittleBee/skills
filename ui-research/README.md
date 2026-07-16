# ui-research

A Claude Code skill that turns a UI question into an evidence-backed research report: which real products do it well, what it looks like, how the interaction feels, how to implement it, and which design principles justify it. The deliverable is a self-contained HTML report opened in your browser, plus a short TL;DR in chat.

Built for the "I want design taste, not platitudes" workflow: every claim must trace to something that actually exists (a product page, an official doc, a line of your own code), and the agent is required to read your project before recommending anything.

## Usage

Install with the Skills CLI (`npx skills add ZingerLittleBee/skills@ui-research`, add `-g` for user-level), or place this directory at `~/.claude/skills/ui-research/` (user-level) / `<project>/.claude/skills/ui-research/` (project-level). Claude triggers it automatically on UI-research-shaped requests — no slash command needed.

Example prompts that trigger it:

```text
帮我调研一下优秀 macOS app 的设置页都是怎么设计的，把结果整理给我看
调研一下现在原生 macOS 工具类 app 流行的 UI 风格，给我个报告
我们要做官网 landing page，调研下优秀开发者工具的官网，重点看排版和动效
how do good apps implement command palettes? show me references
```

Both concrete components (a settings window, a sidebar) and vague directions (current style trends) work; for vague ones the report states the scope it chose so you can redirect.

### Output

- `.claude/ui-research/<topic-slug>/report.html` under the current working directory (plus local screenshots), opened in the browser automatically. Not meant to be committed.
- A chat summary with the report path and the TL;DR decisions.

The report opens with 3–5 actionable decisions (each naming its best reference), followed by the research dimensions the question needed — visual references, interaction & motion, implementation, design principles — and ends with a limitations section (research date, what couldn't be verified, screenshots that couldn't be captured and why).

## What makes it trustworthy

These rules are enforced by the skill and covered by its eval assertions:

- **Repo grounding** — before any claim about your project ("you should add X", "you don't use Y"), the agent greps the whole repo and names the files/call sites it checked. Recommendations for things you already implement are treated as failures.
- **Evidence discipline** — product references link to the product's own domain; principle citations link to the specific guideline page and keep the rule's original conditions; disagreements between good references are reported, not averaged away.
- **Screenshots or an explanation** — the visual dimension ships local screenshots (with source/date captions) or an explicit limitation note, never silent text-only.
- **Mechanical output validation** — the report HTML is scanned for unescaped `<`/`&` before delivery so code sketches render intact.

## Layout

```text
ui-research/
├── SKILL.md                    # the skill itself (workflow + rules)
├── references/sources.md       # curated source map per research angle
├── assets/report-template.html # report skeleton and styling
└── evals/evals.json            # test prompts + assertions (format/quality split)
```

## Development

Iterated three rounds with skill-creator: with-skill runs vs no-skill baselines, graded on format-compliance and research-quality assertion groups, with adversarial verification (independent repo greps, per-image caption checks, verbatim citation fetches). Round-3 result: with-skill 45/45 across three test cases vs baseline 21/45. Eval workspaces live outside the skill (`../ui-research-workspace/iteration-N/`).
