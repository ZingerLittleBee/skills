# design-parity profile

Filled profile for amux, a macOS SwiftUI app restored from a Design Compiler
mockup. Kept here as the calibration example for [setup.md](../setup.md).

## Design files

- Markup and CSS: `docs/design/amux-v2-markup.html`. Dark tokens: the
  `:root { … }` block. Light override: `html[data-amux-theme="light"] { … }`.
  Sixty-two tokens defined across both.
- Prototype logic: `docs/design/amux-v2-logic.js`. Initial state in
  `initial()`, layout arithmetic in `renderVals()`, drag clamps in
  `dragSidebar` (200…400) and `dragDrawer` (260…560), theme and settings
  transitions in `setTheme()` and the settings `theme` select handler.
- Renderable locally: no. The markup is a Design Compiler template (`{{ }}`
  bindings, `<x-dc>`) and its runtime is not in the repo. Derive expected
  values from source.
- Base design system: Claude Design project `Substrate Design System`
  (`5d160f0b-5839-4211-9c5d-230fdda47a69`), read with `DesignSync get_file`.
  Tokens the markup uses without defining, the only ones to take from it:
  `--dur-fast` = 120ms and `--ease-out` = `cubic-bezier(.16,1,.3,1)`, both in
  `tokens/motion.css`. The rest of that project is a monochrome brand with
  Geist fonts; the amux palette is indigo-accented with SF Mono.
- Reference screenshots: none yet. The prototype preview size is 1440×900;
  export from Claude Design in both themes into `docs/design/reference/`.

## App counterparts

- Token module: `Sources/AmuxDesign/DesignPalette.swift`, `DesignMetrics.swift`,
  `DesignTypography.swift`, `DSMetrics.swift`. `color-mix(in oklab, …)` values
  are stored as precomputed sRGB with the CSS in a comment beside each.
- Layout arithmetic: `Sources/AmuxUI/Shell/WindowSizeClass.swift`
  (`WindowSizeClass`, `WindowFrameLayout`).
- Existing parity tests: none. Test target `AmuxDesignTests`, run with
  `swift test -c debug --filter AmuxDesignTests`.

## Building and driving the app

- Build: `make build`.
- Reset scratch state: `make scratch-reset SESSION=amux-parity` and
  `defaults delete amux.scratch`. Session names must not be `default`.
- Launch against scratch state, in the background:
  `make run-scratch SESSION=amux-parity`. It sets
  `AMUX_DEBUG_CONTROL_DIR=.build/scratch/control`.
- Control channel: append one JSON line to `.build/scratch/control/in.jsonl`;
  the harness appends the answer to `out.jsonl` with the same `id`. Wait for
  the matching `id` before sending the next request.

  ```
  {"id":"q1","op":"query"}
  {"id":"c1","op":"call","name":"setWindowWidth","arg":"1000"}
  {"id":"s1","op":"screenshot","arg":"/abs/path/shot.png"}
  {"id":"k1","op":"command","name":"<AppCommand rawValue>"}
  ```

- Read state: `op: query`. Keys that matter: `frame` (derived
  `WindowFrameLayout`: `sizeClass`, `sidebarWidth`, `drawerWidth`,
  `sidebarFloat`, `drawerFloat`, `overlayScrim`, `showBareLights`), `layout`
  (stored widths, `drawerTab`, `windowWidth`), `overlays` (modal, palette,
  context menu and its clamped anchor), `tabs`, `panes`, `dividers`, `strip`,
  `theme`, `toast`.
- Model-level operations (`op: call`):

  | name | arg | effect |
  | --- | --- | --- |
  | `setWindowWidth` | width in points | layout model only, not the real window |
  | `dragSidebar` / `dragDrawer` | translation in points | begin, update, end on the model |
  | `setSetting` | `theme=Substrate dark` / `theme=Substrate light`, `fontSize=…` | settings |
  | `openPalette`, `palette`, `runPalette`, `escape` | query text for `palette` | palette flow |
  | `newTab`, `splitRight`, `splitDown`, `closeTab`, `confirmCloseTab`, `cancelCloseTab` | tab or panel id where needed | pane and tab model |
  | `setDrawerTab`, `drawerShortcut` | tab name / zero-based index 0–3 | drawer |
  | `addDirectory` | absolute path | seeds a worktree so tabs exist |

- Real-input operation for hit-testing: `mouseDrag` with arg `"x,y,dx,dy"`,
  window points from the top-left corner. Queues a press, eight drag steps,
  and a release through `NSApp.postEvent`; drives SwiftUI `DragGesture` and
  `Button` reliably.
- Screenshot: `op: screenshot` with an absolute output path; captures the
  content view at backing scale, 2× on Retina.
- Real window resize: needed for rendered breakpoints.
  `osascript -e 'tell application "System Events" to tell process "amux" to set size of front window to {1000, 760}'`,
  then confirm `layout.windowWidth` through `query`.
- Theme switch: `setSetting` with `theme=Substrate light` or
  `theme=Substrate dark`.
- Seed data: `addDirectory` with an absolute repo path, then `newTab`.

## Pitfalls already paid for

- Synthetic CGEvents from an outside process and `window.sendEvent` do not
  reach SwiftUI gestures; a "no change" from them proves nothing. Only
  `mouseDrag` counts.
- Accessibility frames of SwiftUI views come back about 24 pt left of the
  rendered position. Use harness screenshots for geometry, AX only for presses.
- Layout and theme persist in the `amux.scratch` defaults suite, and a
  bundled Herdr session survives quit. Reset both between runs.
- `setWindowWidth` changes the model, so `frame` follows but pixels do not.

## Scenarios beyond the default set

- Layout formulas from `renderVals()`:

  ```
  size    = vw<720 xs | vw<900 sm | vw<1180 md | vw<1440 lg | else xl
  sidebar = sm:204 | md:min(stored,224) | lg,xl:stored        clamp 200…400
  drawer  = xs,sm: max(258, min(336, vw-112)) | md:min(stored,304) | else stored   clamp 260…560
  sidebarFloat = xs ; drawerFloat = true ; rail = 44
  centre  = vw - sidebar - (drawer open ? drawer : 44) - 8
  ```

  Default stored widths are 252 and 344.
- Context menu anchor clamps at `window.innerWidth - 240` in the prototype;
  the app reports `overlays.contextMenuClamped`.
- Drawer shortcuts are Opt 1…4 and go through `drawerShortcut`; the palette's
  drawer commands are `AppCommand`s and go through `op: command`.
