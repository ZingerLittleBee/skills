---
name: unslop
description: Use when the user explicitly asks to humanize, polish, rewrite, or remove AI-sounding patterns from English or Chinese prose. Do not invoke for ordinary drafting, factual review, translation, or code changes unless this editing pass is requested.
---

# Unslop

Remove formulaic AI writing patterns while preserving the author's meaning and voice.

## Boundaries

1. Apply this skill only when the user explicitly requests polishing, humanizing, rewriting, or removing AI-sounding prose.
2. Preserve code, commands, quotations, proper nouns, technical terms, citations, and other exact text unless the user asks to edit them.
3. Do not invent facts, opinions, emotions, anecdotes, certainty, or source claims. Add personality only by sharpening wording already supported by the source.
4. Treat pattern lists as diagnostic signals, not banned-word lists. Keep wording that is precise, idiomatic, or required by the domain.

Preserve the requested language, Chinese script and regional terminology. Preserve the source's intent, factual claims, confidence, point of view, and required format.

## Workflow

1. Identify the intended audience, tone, and language from the request and source. Ask only when the missing choice would materially change the result.
2. Mark protected spans and factual claims before rewriting.
3. Read only the matching language guide:
   - For English prose, read [references/english.md](references/english.md).
   - For Chinese prose, read [references/chinese.md](references/chinese.md).
   - For mixed prose, read both and apply each guide to its own language.
4. Rewrite the passage. Prefer concrete actors, actions, mechanisms, examples, and numbers already present in the source.
5. Self-audit: "What still makes this sound generated, and did the rewrite change anything it was not authorized to change?" Fix the remaining tells and restore any lost meaning.

Return the rewritten text directly unless the user requests an explanation, alternatives, or a change log.
