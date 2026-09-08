# design-parity profile

Illustrative profile for a React app whose design is a React prototype: a
Vite workspace with the prototype under `design/` and the product under
`app/`, both driven through the chrome-devtools MCP. Paths and ports are
placeholders; the shape is what to copy.

## Design files

- Markup and CSS: `design/src/tokens.css`. Dark tokens: `:root`. Light
  override: `[data-theme="light"]`. Component markup in `design/src/**/*.tsx`.
- Prototype logic: `design/src/state.ts`. Initial state in `initialState`,
  layout arithmetic in `layoutFor(viewportWidth, state)`, drag clamps in
  `useResizeDrag` (`min`, `max` arguments), theme and settings transitions in
  `reducer`.
- Renderable locally: yes. `pnpm --filter design dev` serves it at
  `http://localhost:5174`; expected values are measured there, not derived.
- Base design system: none. Every token the prototype uses is defined in
  `tokens.css`.
- Reference screenshots: captured on demand from the running prototype at
  1440×900, device scale factor 1, into `.design-parity/reference/`.

## App counterparts

- Token module: `app/src/styles/tokens.css` (must mirror the design file
  name for name) and `app/tailwind.config.ts` `theme.extend` where Tailwind
  utilities are used.
- Layout arithmetic: `app/src/layout/frame.ts` (`frameFor`).
- Existing parity tests: `app/src/styles/tokens.test.ts` compares both
  token files; run with `pnpm --filter app test tokens`.

## Building and driving the app

- Build: `pnpm install && pnpm --filter app build`.
- Reset scratch state: `localStorage.clear()` through `evaluate_script`
  before each scenario; the app persists layout widths and theme under the
  `app.layout` and `app.theme` keys.
- Launch, in the background: `pnpm --filter app preview --port 4173` for the
  built bundle, `pnpm --filter design dev` for the prototype.
- Control channel: chrome-devtools MCP. `new_page` for each side, `select_page`
  to switch, `navigate_page` to load a route, `wait_for` on a selector before
  reading.
- Read state: `evaluate_script` returning a JSON object. Rectangles through
  `el.getBoundingClientRect()` on `[data-testid]` elements; computed colours
  through `getComputedStyle(el).backgroundColor`; stored widths through
  `JSON.parse(localStorage.getItem('app.layout'))`. Keys that matter:
  `sizeClass`, `sidebarWidth`, `drawerWidth`, `sidebarFloat`, `drawerFloat`.
- Model-level operations:

  | operation | how | effect |
  | --- | --- | --- |
  | viewport width | `resize_page` width, height | real resize; both `layoutFor` and rendering follow |
  | stored width | `evaluate_script` writing `app.layout` then `navigate_page` reload | seeds a width above a cap |
  | theme | `click` on `[data-testid=theme-toggle]` or `evaluate_script` setting `data-theme` | theme |
  | route | `navigate_page` | which panels exist |

- Real-input operation for hit-testing: `drag` from the handle's
  `[data-testid]` element to a target offset, or `click` followed by
  `press_key`. Coordinates come from `take_snapshot` uids, not from guessed
  pixels.
- Screenshot: `take_screenshot` with `fullPage: false`; scale 1× when
  `emulate` sets `deviceScaleFactor: 1` on both pages.
- Real window resize: not needed; `resize_page` is the window.
- Theme switch: `evaluate_script` with
  `document.documentElement.dataset.theme = 'light'`.
- Seed data: the app reads `VITE_FIXTURE=parity` at build time and mounts the
  same fixture the prototype ships with.

## Pitfalls already paid for

- `resize_page` below 720 px triggers the prototype's mobile layout, which the
  app does not implement; scope the xs class out unless the profile owner
  says otherwise.
- Tailwind's JIT drops utilities never referenced in source; a token that is
  defined but produces no class is `unused in design`, not a mismatch.
- `getBoundingClientRect` includes CSS transforms; read a dragging handle
  after the transition ends (`wait_for` on `[data-dragging=false]`).
- Both pages share one browser profile; clear `localStorage` per page, not
  once per run.

## Scenarios beyond the default set

- Layout formulas from `layoutFor()`:

  ```
  size    = vw<720 xs | vw<900 sm | vw<1180 md | else lg
  sidebar = sm:200 | md:min(stored,240) | lg:stored          clamp 180…360
  drawer  = xs,sm: min(320, vw-96) | md:min(stored,320) | lg:stored   clamp 240…520
  ```

- Keyboard: `Mod+B` toggles the sidebar, `Mod+J` the drawer, `Escape` closes
  the topmost overlay only.
- Context menu is anchored at the pointer and flips left when
  `x + 220 > vw`.
