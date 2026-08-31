# Improve Tauri Accessibility and Automation

## Objective

Improve and verify accessibility in a Tauri desktop application. Accessibility and automation coverage must independently exercise the WebView, native Tauri UI, and Rust command state boundaries.

## Validation layers

- Use `better-accessibility` to review the WebView frontend code.
- Use `agent-browser` to inspect DOM structure and accessibility semantics in standard browser development mode.
- Prefer the project's existing WebdriverIO configuration. If the project already uses `@wdio/tauri-service`, use it to run end-to-end tests against the real Tauri application.
- Use `computer-use:computer-use` to inspect the actual macOS accessibility tree and click behavior of the packaged or development Tauri application.
- Do not assume that passing in a standard browser means the Tauri WebView or other operating systems also pass.

## Areas to inspect

### 1. WebView accessibility

- Use native semantic elements such as `button`, `a`, and `input`.
- Give controls stable accessible names, roles, and states.
- Ensure that all primary workflows can be completed with the keyboard.
- Ensure that dialogs, menus, lists, tabs, and forms have correct focus behavior.
- Prefer role and accessible name selectors in automation.
- Use `data-testid` only as a fallback when semantic selectors are insufficient.

### 2. Tauri windows and native UI

- Check close, minimize, maximize, and back buttons in custom title bars.
- Ensure that `data-tauri-drag-region` does not cover interactive controls or swallow their clicks.
- Ensure that drag regions, transparent layers, and decorative layers do not intercept button events.
- Verify that native menus, tray menus, file pickers, permission prompts, and system dialogs are identifiable through the operating system accessibility tree.
- A working WebView does not prove that native menus and system dialogs work. Verify them separately.

### 3. Rust command states

- After an `invoke` call starts, expose an explicit loading or `aria-busy` state in the UI.
- Success, failure, and cancellation results must update an observable UI state.
- Do not report errors only through logs. Surface them through form errors, `role="alert"`, or `role="status"`.
- Automation must wait for observable states and must not rely on fixed sleeps.
- Prefer the Tauri APIs, command mocking, and log capture capabilities provided by `@wdio/tauri-service`.
- Use mocks only at operating system or external service boundaries. Do not use mocks to hide real UI interaction problems.

### 4. Cross-platform differences

- macOS uses WKWebView, Windows uses WebView2, and Linux uses WebKitGTK. Their accessibility mappings may differ.
- Mark platforms that cannot be tested on the current machine as `Not verified`.
- Do not claim that every platform passes based on results from a single platform.

## Completion criteria

- Run one WebView semantic check in standard browser mode.
- Complete one full keyboard workflow in a real Tauri window.
- Use Computer Use to obtain the application accessibility tree and click critical controls through the latest `element_index`.
- Refresh the state after every click and verify the resulting UI change.
- Run at least one critical E2E workflow using the existing WebdriverIO or `@wdio/tauri-service` setup.
- Cover the loading, success, and error states of at least one Rust command.
- Do not use coordinate-based clicks unless the accessibility tree is genuinely unavailable. When this happens, record the affected control and root cause.
- Explicitly mark platforms that cannot be tested on the current machine as `Not verified`. Do not infer that they pass.

Mark the goal complete only after every validation item that can run in the current environment has produced observable evidence. If an environment or permission issue prevents validation, record the exact blocker instead of guessing the result.
