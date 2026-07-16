# Where to look, per research angle

A curated starting map. It is a floor, not a ceiling — search beyond it when the topic demands, but check the relevant rows here first.

## Principles (cite these next to recommendations)

| Source | URL | What it's for |
|---|---|---|
| Apple Human Interface Guidelines | developer.apple.com/design/human-interface-guidelines | The authority for anything native Apple-platform. Has per-component pages (e.g. /settings, /sidebars, /windows) — cite the specific page. |
| Refactoring UI (summaries/site) | refactoringui.com | Engineer-friendly visual rules: hierarchy via weight/color not size, spacing over borders, shadow usage. |
| Web Interface Guidelines | interfaces.rauno.me | Checklist of interaction details for web UI: focus states, cursors, touch targets. |
| Laws of UX | lawsofux.com | Interaction psychology (Fitts, Hick, aesthetic-usability). Short, citable. |
| Material 3 | m3.material.io | The authority for Android/Material contexts; also useful cross-platform for component anatomy pages. |
| Fluent 2 | fluent2.microsoft.design | Windows-native contexts. |
| WCAG quick reference | www.w3.org/WAI/WCAG22/quickref/ | Accessibility requirements — cite the specific success criterion when a recommendation touches contrast, focus, or motion. |
| Nielsen Norman Group | nngroup.com | Usability research articles; good for pattern-level "does this actually work" evidence. |

## Interaction & motion

| Source | URL | What it's for |
|---|---|---|
| Emil Kowalski's blog | emilkowal.ski | When to animate and when not to; UI polish details. |
| Rauno Freiberg — craft | rauno.me/craft | Interaction design essays with video examples. |
| Josh Comeau | joshwcomeau.com | Spring animations and CSS motion, deeply explained. |

## Visual reference galleries

| Source | URL | Notes |
|---|---|---|
| Mobbin | mobbin.com | Real product screenshots by pattern. Mostly login-gated — fall back to product marketing pages if blocked. |
| Godly | godly.website | Curated web design. |
| Land-book | land-book.com | Landing page gallery. |

## Products worth inspecting directly

- **Native macOS**: Things 3, Raycast, CleanShot X, Craft, Fantastical, Apple's own system apps (Notes, Settings, Freeform). Their marketing sites show real UI at high resolution.
- **Web / dev tools**: Linear, Vercel, Stripe, Resend. Linear's site and app are the current taste benchmark for tool UI.

## Implementation evidence

- **GitHub search for open-source apps with the same UI.** For SwiftUI: search `<component> SwiftUI macOS` and read real code from apps like Ice (menu bar manager), CodeEdit, or whatever the search surfaces with stars and recent commits. Reading a shipped implementation beats any tutorial.
- **Official framework docs** for the exact APIs (e.g. SwiftUI `Settings` scene, `NavigationSplitView`; CSS `@view-transition`).
- **Well-known libraries** only if maintained and widely used — name adoption evidence (stars, who uses it).

## Search tips

- `site:developer.apple.com/design <topic>` finds the exact HIG page fast.
- For "what does X app's Y screen look like": try the product's own marketing/press pages, then App Store screenshots, then YouTube reviews (frame captures).
- For trends ("what's current"): recent posts from the motion/craft blogs above + what the benchmark products shipped this year, not trend listicles.

## Timeliness

Trend claims rot fast. Prefer sources from the last ~2 years for anything phrased as "current" or "流行"; when citing a screenshot or article, note its date. A marketing page may show an older UI than the shipping product — when the report's claim depends on the *current* version, say which version the evidence shows. Framework behavior claims ("X is required", "Y is the default") must be verified against the official docs for the current release, not blog posts.
