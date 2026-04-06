# Accessibility Notes

## Verified current state

Verified by inspection:

- [`src/occams_beard/templates/layout.html`](../src/occams_beard/templates/layout.html) includes a skip link and a focusable main landmark.
- [`src/occams_beard/templates/index.html`](../src/occams_beard/templates/index.html) uses explicit labels, field descriptions, fieldsets, legends, and alert semantics across both the self-serve and guided-support flows.
- [`src/occams_beard/templates/index.html`](../src/occams_beard/templates/index.html) keeps the self-serve symptom flow server-rendered, and the inline plan-loading shell is enhancement-only, so the recommended plan can still be loaded and run when JavaScript is unavailable or the fetch path fails.
- [`src/occams_beard/templates/run_progress.html`](../src/occams_beard/templates/run_progress.html) now includes a dedicated polite live region for major run-state changes in addition to visible status text.
- [`src/occams_beard/templates/results.html`](../src/occams_beard/templates/results.html) gives clearer export guidance, uses explicit text status pills, and makes the support-bundle handoff primary in support mode without removing the secondary rerun/export paths.
- [`src/occams_beard/static/style.css`](../src/occams_beard/static/style.css) adds visible `:focus-visible` outlines, selected-state fallback classes for grouped controls, and explicit `@media (prefers-reduced-motion: reduce)` and `@media (forced-colors: active)` handling for controls, progress states, and status surfaces.
- [`src/occams_beard/templates/index.html`](../src/occams_beard/templates/index.html) uses plain-language symptom choices for self-serve entry and keeps advanced controls behind progressive disclosure.

Verified by unit test:

- [`tests/test_app.py`](../tests/test_app.py) checks for the two entry paths, symptom-led self-serve copy, the guided-support bridge, the conditional self-serve clarification copy, the progress payload live-status fields, and the visible support-bundle warning shell.
- [`tests/test_browser_ui.py`](../tests/test_browser_ui.py) adds opt-in Safari/WebDriver coverage for keyboard entry-path selection, JavaScript symptom auto-loading as a progressive enhancement, native `<details>` behavior, active progress-row emphasis, and mode-specific CTA ordering. The test suite skips cleanly when Safari WebDriver is unavailable.

## What remains unverified

Not verified by repository artifacts:

- actual VoiceOver or NVDA spoken output
- manual keyboard behavior in a non-headless desktop browser session on the current host
- Safari/WebKit assistive-technology behavior outside the opt-in WebDriver path
- forced-colors behavior in a real high-contrast environment
- reduced-motion behavior in a real browser with OS-level motion reduction enabled
- formal WCAG conformance

Actual screen-reader speech output is not verified by this repository.

## Recommended next audit steps

1. Perform a manual keyboard-only pass in desktop Chrome and Safari against both `/` and `/results/<run_id>`.
2. Repeat the same pass with `prefers-reduced-motion` enabled and confirm that smooth scrolling, button/card transitions, and progress-meter updates stay calm and do not introduce extra motion.
3. Validate the entry flow, progress page, and support-bundle controls in Windows High Contrast or another forced-colors-capable environment.
4. Run a VoiceOver pass on macOS and record heading, landmark, form-control, live-region, and export-flow behavior.
5. If a Windows validation path becomes available, run the same results flow with NVDA and record any divergences.
