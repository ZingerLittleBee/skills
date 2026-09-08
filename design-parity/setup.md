# design-parity — first-run setup

`.design-parity/project.md` is the project profile the review runs on. Write
it yourself from what the project actually contains: inspect the design
files, the design module, the debug or automation hooks, the task runner, and
`CLAUDE.md` / `AGENTS.md`. A profile built from guesses produces findings that
are probe failures.

1. Create the directory and write the [template below](#template) verbatim,
   then replace every placeholder with a real value.
2. For each section, look before you write:
   - **Design files**: find the mockup, its token block per theme, and the
     prototype logic. Count the tokens the markup uses but never defines;
     those are the only ones a base design system may supply.
   - **App counterparts**: the module that transcribes tokens, the type that
     holds layout arithmetic, any existing parity test.
   - **Driving the app**: the debug harness, control channel, automation
     hook, or accessibility path the project already has. Record the exact
     protocol: how to send an operation, how to read the answer, which
     operations change the model, which inject real input, how to take a
     screenshot, how to resize the real window if the model-level width does
     not.
   - **Pitfalls**: what the project's docs, memory notes, and review records
     say cost time before. Copy them; do not rediscover them.
   - **References**: whether prototype screenshots exist and at what size.
3. Show the user the filled profile and confirm the build, launch, and reset
   commands before running anything.
4. Reports are meant to be committed; scratch output is not. Offer to add:

   ```gitignore
   .design-parity/*
   !.design-parity/project.md
   !.design-parity/reports/
   ```

Two filled profiles calibrate the level of detail: every operation named,
every argument format shown, every pitfall one line.

- [examples/amux-project.md](examples/amux-project.md): a SwiftUI app with a
  JSON-line debug harness, prototype not renderable locally.
- [examples/react-project.md](examples/react-project.md): a React app driven
  through a browser, prototype renderable alongside it.

## Template

### `.design-parity/project.md`

```markdown
# design-parity profile

## Design files

- Markup and CSS: `<path>`. Dark tokens: `<selector>`. Light override: `<selector>`.
- Prototype logic: `<path>`. Initial state in `<function>`, layout arithmetic in
  `<function>`, drag clamps in `<methods>`, theme and settings transitions in `<methods>`.
- Renderable locally: yes | no (<why>; derive expected values from source).
- Base design system: none | `<name, location, how to read it>`. Tokens the markup
  uses without defining, the only ones to take from the base: `<list with values>`.
- Reference screenshots: none | `<dir>`, `<width>×<height>`, one per scenario and theme.

## App counterparts

- Token module: `<paths>`.
- Layout arithmetic: `<path>` (`<types>`).
- Existing parity tests: none | `<test target and command>`.

## Building and driving the app

- Build: `<command>`.
- Reset scratch state: `<commands, including any defaults suite or session store>`.
- Launch against scratch state, in the background: `<command>`.
- Control channel: `<where requests go, where answers appear, request shape, how
  to match an answer to a request>`.
- Read state: `<operation>`; keys that matter: `<list>`.
- Model-level operations and argument formats: `<table>`.
- Real-input operation for hit-testing: `<operation, argument format, coordinate space>`.
- Screenshot: `<operation and output>`; backing scale: `<1× | 2×>`.
- Real window resize: `<not needed | command>`, confirm via `<state key>`.
- Theme switch: `<operation and values>`.
- Seed data so panels and tabs exist: `<operation>`.

## Pitfalls already paid for

- <one line each: what looked like a finding and was a probe failure, what state
  leaks between runs, what coordinate source is unreliable>

## Scenarios beyond the default set

- <project-specific interactions the four layers would not enumerate on their own>
```
