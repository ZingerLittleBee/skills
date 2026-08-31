# Improve Electron Accessibility and Automation

## Objective

Complete one round of accessibility and automation-readiness improvements.

Do not stop after producing an audit report. Inspect, fix, and verify the project's critical interactions so that controls in both the Web panel and Electron desktop application can be consistently identified, located, operated, and verified by assistive technologies and automation tools.

## Capabilities to use

- Use `better-accessibility` to guide code review and remediation.
- Use `agent-browser` to verify the Web panel accessibility tree, keyboard behavior, and real click workflows.
- Use `computer-use:computer-use` to verify the Electron/macOS accessibility tree and click behavior.

## Before starting

1. Read and follow `AGENTS.md`, `CLAUDE.md`, and relevant design documentation in the repository and target directories.
2. Inspect the current Git status and existing changes. Preserve user changes unrelated to this task.
3. Investigate existing components, test frameworks, and automation tooling. Do not build duplicate infrastructure.
4. Do not directly modify the shadcn/ui files under `apps/user-panel/components/ui/`.
5. Do not add dependencies, push code, create a pull request, deploy, or perform a real platform publication without confirmation.

## Scope and priority

Work through the following areas in priority order:

1. Navigation, forms, dialogs, dropdown menus, tabs, list actions, task creation, and publishing workflows in `apps/user-panel`.
2. Reused business components, fixing root causes at the shared component layer whenever practical.
3. User-visible Electron interfaces and critical local controls in `apps/desktop`.
4. Fix HIGH and MEDIUM issues first. LOW issues may be addressed when doing so does not expand the task scope.

## Accessibility requirements

- Use native semantic elements such as `button`, `a`, `input`, and `select` for actions. Avoid `div onClick` and `span onClick`.
- Every interactive control must expose a correct and stable accessible name, role, and state.
- Icon buttons must have explicit `aria-label` values. Decorative icons must use `aria-hidden="true"`.
- Correctly expose states such as `disabled`, `expanded`, `selected`, `checked`, `invalid`, and `busy`.
- Every mouse action must have a keyboard path with correct Tab, Enter, Space, Escape, and arrow-key behavior.
- When a dialog opens, move and constrain focus correctly. When it closes, restore focus to the triggering control.
- Preserve a visible `:focus-visible` style. Do not remove outlines without an equivalent replacement.
- Associate form fields with the correct labels, error descriptions, and `aria-invalid` state.
- Expose dynamic results, loading states, and errors through appropriate status, alert, or `aria-describedby` semantics.
- Provide reasonably sized click targets. Decorative layers must not intercept clicks; use `pointer-events: none` when appropriate.
- Do not apply `aria-hidden="true"` to focusable elements.
- Prefer native semantics. Do not use unnecessary or incorrect ARIA to patch an invalid structure.

## Automation-readiness requirements

- Critical controls must be consistently locatable by role and accessible name within the current context.
- Disambiguate repeated list actions through their row, object name, or scoped container.
- Accessible names must not depend on random IDs, temporary state, or unstable presentation structure.
- Prefer semantic locators such as `getByRole`, `getByLabel`, and `getByText` in automation tests.
- Use a stable `data-testid` only when semantic locators are genuinely insufficient. Do not use it instead of missing accessibility semantics.
- Do not rely on coordinates, DOM hierarchy, `nth-child`, or stale cached element indexes.
- When using Computer Use, refresh the accessibility tree after every UI change and act through the latest `element_index`.
- After every click, read the UI state again and verify the expected `selected`, `expanded`, or `disabled` state, page title, or content change. A call that returns without an error is not evidence of success.
- If the accessibility tree does not expose a control, use screenshots and coordinate clicks only as a fallback and record the root cause.

## Validation requirements

1. Complete one critical workflow using only the keyboard.
2. Inspect the accessible name, role, and state of critical controls in the accessibility tree.
3. Use `agent-browser` to execute at least one critical Web workflow and verify the result after every click.
4. Use Computer Use to execute at least one side-effect-free Electron/macOS click workflow.
5. Do not perform a real social-platform publication, send external messages, or complete any other externally visible final action.
6. Run the existing tests related to the changes, `bun check`, and applicable type checks.
7. Do not hide type errors, disable rules, or weaken test requirements to make checks pass.

## Delivery requirements

- Fix discovered issues in the code. Do not stop at recommendations.
- Report changed files with line references.
- Summarize findings, fixes, and validation evidence under HIGH, MEDIUM, and LOW severities.
- Report static code validation, accessibility-tree validation, keyboard validation, and real-click validation separately.
- Mark checks that could not run as `Not verified`. Do not guess that they passed.
- If any HIGH issue remains, give a final verdict of `Block`. Otherwise, give a verdict of `Approve` and list the remaining MEDIUM and LOW work.
- If code changes were made, create one local Conventional Commit that follows repository conventions. Do not push, create a pull request, or deploy.

## Completion criteria

Mark the goal complete only after the required inspection, remediation, feasible validation, evidence report, and local commit are complete. Preserve all authorization boundaries above. Record exact blockers and mark unavailable checks as `Not verified` instead of inferring success.
