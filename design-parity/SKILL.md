---
name: design-parity
description: "Measure how faithfully an app, native or web, reproduces its HTML or React design mockup and its interactions, layer by layer, and report every divergence with evidence."
disable-model-invocation: true
---

# design-parity — verify a UI restoration against its design

You are the **parity reviewer**. The app under review was restored from an
HTML design (markup, CSS tokens, prototype logic) by someone else, usually
another agent. Your job is to measure, not to judge by eye: every divergence
you report carries an expected value, an observed value, and the method that
produced both. You edit nothing under the app's sources, tests, or design
files. A bug you find is described; the fix is a separate task.

An optional **scope** in the invocation (`sidebar`, `drawer resize`, `light
theme`) narrows the run to the layers and scenarios that touch it. With no
scope, run every layer.

## Project profile

`.design-parity/project.md` at the project root holds everything that differs
between projects: where the design files are, which block is the token
source, how to build and drive a scratch instance of the app, how to read its
state and take screenshots, the probe pitfalls already paid for, and where
reference screenshots live. Read it first. If it is missing, follow
[setup.md](setup.md) and return here once it exists.

The profile overrides this skill wherever the two disagree; it also carries
the project's `CLAUDE.md` and `AGENTS.md` rules by reference. Read those too.

## Sources of truth

Rank them and keep the ranking in view for the whole run:

1. The design's own token block and markup. The profile names the file and
   the selectors for each theme.
2. The prototype logic: initial state, the layout arithmetic, the drag
   clamps, the state transitions behind each handler.
3. A base design system the design inherits from, if any. Only the tokens
   the design **uses without defining** may be taken from it; the profile
   lists which. Everything else in the base is a different brand and reading
   it pollutes the comparison. Take nothing else from it, and do not load a
   base system's own skill or prompt file.
4. Reference screenshots of the prototype, when the profile says they exist.

A design authored in a compiler or template format often cannot be rendered
outside its editor. Expected numbers then come from **reading** the source,
never from running it. The profile says which case applies.

## Environment

Build and launch the app against scratch state exactly as the profile
describes, in the background, and reset that state between runs: stored
layout widths and theme leak from the previous run otherwise, and a leaked
width reads as a finding.

Before trusting any divergence that could be a probe failure, run a
**control**: the same probe against the previous build or the main branch. A
probe that shows "no change" on both sides is broken, not evidence.

## Layer 1: tokens

Parse every token from the design's token block and each theme override, add
the permitted base-system fallbacks, and compare each with its counterpart in
the app's design module. Computed colours (`color-mix`, alpha over a known
surface) are stored precomputed on the app side; recompute them the same way
the CSS specifies and allow ±1 per 8-bit channel. Produce one row per token:

| token | design dark | design light | app dark | app light | status |

Status is `match`, `off by <delta>`, `missing in app`, or `unused in design`.
If the project already has a token parity test, run it and cite the result
instead of parsing again. The layer is complete when every token defined in
the design has a row.

## Layer 2: layout arithmetic and clamps

Transcribe the prototype's layout formulas into one block: size-class
breakpoints, per-class widths and caps, drag clamps, float and overlay
rules, the centre-width equation. Then design scenarios that exercise every
branch of every formula: one width on each side of each breakpoint, a drag
past each clamp in both directions, a stored width above each cap. For each
scenario drive the app, read its layout state, and record expected versus
actual in a table.

Model-level width changes are cheap; use them for the whole table. When the
profile says the app's window must be resized for real to affect rendering,
resize it and confirm through the state read that the app saw the new width,
then take one screenshot per size class per theme.

## Layer 3: interactions

Enumerate the prototype's handlers: theme changes, resize drags, split drags,
keyboard bindings, tab close and confirm, palette, drawer or panel
shortcuts, context-menu placement. For each handler:

1. State the prototype's rule in one line with its source line number.
2. Perform the equivalent in the app. Use the profile's model-level driver
   for state transitions and its real-input driver for **hit-testing**: the
   handles, dividers, and drag regions whose behaviour depends on what sits
   under the cursor.
3. Read the app state before and after and compare the fields the rule
   touches.

Hit-testing must go through real input at coordinates taken from an app
screenshot, then confirm through state that the intended value moved by the
drag distance within its clamp. A handle that does not move its value is one
finding; a handle that also moves something it should not (the divider behind
it, the window itself) is a second.

## Layer 4: visual

Only when reference screenshots exist, or when the prototype renders in the
same runtime as the app and can be captured on demand. For each reference,
put the app in the same state (theme, viewport or window size, open panels,
selected tab), take an app screenshot, and compare side by side after
matching scale; the profile says what scale each side captures at.

When the two sides render in different runtimes (a browser prototype against
a native app), text is never pixel-diffed: the fonts differ. When both render
in a browser with the same fonts, region pixel diffs are valid, text
included. Either way, compare layout boxes, fills, hairlines, radii, and
shadows. Work through the checklist and report each difference with the
region's coordinates and the measured values in both images:

- Column widths, header height, strip heights, rail width.
- Padding and gaps inside rows, tabs, panel sections.
- Hairline colour and placement, sheen presence.
- Surface fills per theme, selection tint, hover and active states where
  the reference shows them.
- Corner radii of cards, popovers, modals, palettes.
- Shadows on floating panels, popovers, modals.
- Text hierarchy: which items read primary, secondary, muted.

Without references, mark the layer `skipped: no reference captures` and say
what capturing them would take.

## Report

Write `.design-parity/reports/<date>-parity.md` and paste its summary in your
final message:

1. A verdict per layer: `pass`, `fail (n findings)`, or `skipped (why)`.
2. Findings, most severe first. Each carries: layer, the prototype rule with
   its source line, the observed value with its method (the driver sequence
   or the screenshot path), the delta, and a severity of `blocker` (wrong
   behaviour or wrong colour), `major` (size or position off by more than
   2 pt), or `minor` (within 2 pt, hover polish, easing).
3. The full tables from layers 1 and 2.
4. Everything you could not measure, and why.

A finding without all three of expected, actual, and method is not a
finding; drop it or go measure. When done, stop the scratch app and reset the
scratch state as the profile describes.
