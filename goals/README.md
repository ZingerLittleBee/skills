# Personal Goals

Reusable goals for long-running Codex work.

## Available goals

- [Electron accessibility and automation](electron-accessibility-and-automation.md): Inspect, fix, and verify accessibility and automation behavior across the Web panel and Electron desktop application.
- [React Doctor perfect score](react-doctor-perfect-score.md): Run React Doctor, fix every issue at its root cause, and reach a verified score of 100 without shortcuts.
- [Tauri accessibility and automation](tauri-accessibility-and-automation.md): Improve and verify accessibility across the WebView, native Tauri UI, Rust command state boundaries, and platform-specific accessibility mappings.

## Usage

Run a goal from the target project. Because this is a private repository, each
command explicitly tells Codex to load the goal through an authenticated GitHub
CLI session. A relative path works only when the goal file is already present in
the current workspace, while `/goal` is not documented as a URL-template loader.

These commands require `gh auth status` to succeed and the corresponding files
to be available on the remote `main` branch.

### Electron accessibility and automation

```text
/goal Load the goal specification by running `gh api -H "Accept: application/vnd.github.raw+json" 'repos/ZingerLittleBee/skills/contents/goals/electron-accessibility-and-automation.md?ref=main'`, then execute every requirement in that document against the current project until all completion criteria are satisfied.
```

### React Doctor perfect score

```text
/goal Load the goal specification by running `gh api -H "Accept: application/vnd.github.raw+json" 'repos/ZingerLittleBee/skills/contents/goals/react-doctor-perfect-score.md?ref=main'`, then execute every requirement in that document against the current project until all completion criteria are satisfied.
```

### Tauri accessibility and automation

```text
/goal Load the goal specification by running `gh api -H "Accept: application/vnd.github.raw+json" 'repos/ZingerLittleBee/skills/contents/goals/tauri-accessibility-and-automation.md?ref=main'`, then execute every requirement in that document against the current project until all completion criteria are satisfied.
```

When the goal file already exists inside the current workspace, use its
workspace-relative path instead of a URL.
