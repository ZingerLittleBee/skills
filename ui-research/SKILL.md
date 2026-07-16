---
name: ui-research
description: Research how excellent products design and implement a piece of UI, then present the findings as a polished local HTML report opened in the user's browser. Use whenever the user wants UI or design research — "调研一下别人怎么做设置页", "看看优秀 app 的 onboarding 长什么样", "研究下现在流行的 UI 风格", "how do good apps implement X" — or asks for design references, visual inspiration, interaction/motion patterns, or implementation approaches for a UI. Trigger for both concrete components (a settings page, a sidebar, a command palette) and vague directions (overall style, current trends), even if the user never says the word "research" or "调研".
---

# UI Research

Turn a UI question into an evidence-backed research report: which real products do it well, what it looks like, how the interaction feels, how to implement it, and which design principles justify it. The deliverable is a self-contained HTML report the user reads in their browser.

The reason this skill exists: when asked for design advice, models tend to produce generic platitudes ("keep it clean, use whitespace") or confident recommendations that don't survive contact with reality. The user wants the opposite — named products, real links, concrete patterns, and advice that accounts for what their project already does. Every claim in the report should be traceable to something that actually exists, and every recommendation should be something the user hasn't already built.

## Step 1: Scope the question

Classify the input before searching:

- **Concrete** ("研究下设置页怎么做") — the unit of research is one component/page/flow. Identify the platform (native macOS/SwiftUI, web, iOS…) from the request or the current repo; the platform changes both which products to inspect and what implementation code means.
- **Vague** ("调研下现在流行的风格") — the unit of research is a style landscape. Narrow it yourself using context (this repo's platform, the user's product) rather than asking; state your chosen scope in the report's overview so the user can redirect if you guessed wrong.

### Ground yourself in the user's project first

If the research is for a specific project, read the relevant source before researching — not just the README, but the actual UI code the recommendations will touch (the existing settings view, the main navigation, the styling layer). You are building a mental diff between "what good looks like" and "what the project has". A recommendation the project already implements is worse than no recommendation: it tells the user you didn't look, and it poisons trust in everything else the report says. Before writing any "you should change X" item, verify in the code that X isn't already true, and name the file you checked.

The same bar applies to statements of fact about the project, not just recommendations. Reading a few files does not license claims about the whole repo: before writing "the project doesn't use X" or "you have no need for Y", grep the entire repo for the API or pattern — a claim one grep would disprove is the fastest way to lose the reader (a report once declared "you don't call the old settings-opening API" while `MenuBarPanel.swift` was calling exactly that). When a claim or recommendation touches a specific API, list the call sites you checked, including the ones that turned up empty.

## Step 2: Research the dimensions the question needs

There are four research dimensions. Pick the ones the question actually calls for — a motion-specific question doesn't need a principles survey padding it out, and a "what's the current style" question may not need code. State in the report's overview which dimensions you chose and in one line why. Broad questions usually deserve all four; don't pad narrow ones.

If a subagent/Task tool is available, fan the chosen dimensions out in parallel; otherwise work through them inline with web search. Consult `references/sources.md` for where to look per dimension and platform — read it before searching.

1. **Visual references** — find 4–8 named products that do this well. For each: what specifically is good (not "looks clean" but "single-window settings with a sidebar of 6 icons, content pane never scrolls horizontally"). Capture a link to the product's own page showing the UI.
2. **Interaction & motion** — how state changes feel: transitions, gestures, springs, timing, what's interruptible. Note *why* the choice works, not just that it exists.
3. **Implementation** — how to actually build it in the target stack. Best evidence: open-source apps with the same UI (GitHub search), official framework APIs, well-known libraries. Verify framework claims against official docs before asserting them ("X is required" vs "X is the default" is exactly the kind of detail that makes or breaks trust). Include short code sketches in the project's language.
4. **Principles** — the specific guideline entries that justify the recommendations: HIG sections, Refactoring UI rules, Web Interface Guidelines items, Laws of UX. Cite the specific rule, with link, next to the recommendation it supports.

Quality bar for evidence:
- Prefer primary sources (the product itself, official docs, the author's own writing) over listicles.
- A link must do two jobs: exist, and actually support the claim next to it. Linking a product's homepage under a claim about its settings page is decoration, not evidence.
- Product references link to the product's own domain, not a round-up article that mentions it.
- If two good products disagree on an approach, show both and say which fits the user's context and why. Disagreement between good references is a finding, not a problem.
- When citing a guideline, keep its conditions. Design rules are usually conditional ("motion that carries meaning must survive Reduce Motion; purely decorative motion may be removed entirely") — flattening a conditional rule into an unconditional one misrepresents the source, and a reader who later reads the original will stop trusting the report.
- Before finalizing, reread the report for internal contradictions — a principles section that says "don't add custom transitions" must not sit above a code sketch that adds one.

### Screenshots

The visual dimension is dramatically better with pictures. If browser automation is available (agent-browser skill, chrome-devtools tools), screenshot the key references — product marketing pages work when the app itself can't be captured — and save them as local PNGs next to the report. If screenshots genuinely can't be captured (no browser tooling, login-walled product, native app with no public imagery), say so explicitly in the report's limitations section instead of silently shipping a text-only visual section. Never hotlink images from other sites (CDN protection breaks them silently).

## Step 3: Build the report

Start from `assets/report-template.html` (copy it, then fill it in — the placeholder comments explain each slot). Keep its styling; the report itself is a taste artifact and should look like the advice it gives.

Report rules:
- Write prose in the language the user is conversing in (for a Chinese conversation, Simplified Chinese). Code — including comments inside code sketches — stays in English, matching professional repo conventions.
- Open with a TL;DR: 3–5 decisions the user could act on today, each naming its best reference.
- Sections follow the dimensions you chose in Step 2.
- Every recommendation carries its evidence inline: product name + link, or principle + link. No orphan advice.
- Project-specific recommendations name the file they were checked against ("现有 `SettingsView.swift` 已是 grouped Form，无需迁移" is a valid and valuable finding).
- Code sketches are illustrative, 5–20 lines, in the target stack — enough to show the approach, not a full implementation.
- End with the limitations section: research date, what couldn't be verified, screenshots that couldn't be captured and why, claims with lower confidence.

### Validate before shipping

HTML fails silently: a literal `<motion.div>` inside a code sketch just vanishes when the browser parses it as a tag, and the reader sees a broken example without knowing it. Escape `&`, `<`, `>` in every text node — especially inside `<pre><code>` — while writing. Then verify mechanically instead of trusting yourself:

```bash
python3 - <<'EOF'
import re, sys
t = open("report.html", encoding="utf-8").read()
bad = []
for m in re.finditer(r"<pre[^>]*>(.*?)</pre>", t, re.S):
    inner = re.sub(r"</?code[^>]*>", "", m.group(1))
    if "<" in inner:
        bad.append("unescaped < inside a code block: " + inner[inner.index("<"):][:60])
for m in re.finditer(r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|[A-Za-z]+;)", t):
    bad.append("raw & at offset %d: %r" % (m.start(), t[m.start():m.start()+30]))
print("\n".join(bad) or "OK")
sys.exit(1 if bad else 0)
EOF
```

Fix anything it flags before delivering.

Save to `.claude/ui-research/<topic-slug>/report.html` under the current working directory (create the directory; it should not be committed). Then open it:

```bash
open .claude/ui-research/<topic-slug>/report.html
```

## Step 4: Present

After opening the report, give the user a short summary in chat: the report path, the TL;DR decisions, and anything surprising the research turned up. The chat summary is a teaser, not a duplicate — details live in the report.
