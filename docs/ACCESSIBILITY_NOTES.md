# Accessibility Notes

## Verified current state

Verified by inspection:

- [`src/occams_beard/templates/layout.html`](../src/occams_beard/templates/layout.html) includes a skip link and a focusable main landmark.
- [`src/occams_beard/templates/index.html`](../src/occams_beard/templates/index.html) uses explicit labels, field descriptions, fieldsets, legends, and alert semantics across both the self-serve and guided-support flows.
- [`src/occams_beard/templates/index.html`](../src/occams_beard/templates/index.html) keeps the self-serve symptom flow server-rendered, so the recommended plan can still be loaded and run when JavaScript is unavailable.
- [`src/occams_beard/templates/results.html`](../src/occams_beard/templates/results.html) gives clearer export guidance, uses explicit text status pills, and explains when `raw-commands.json` will or will not be present.
- [`src/occams_beard/static/style.css`](../src/occams_beard/static/style.css) adds visible `:focus-visible` outlines and focus-within treatment for grouped controls.
- [`src/occams_beard/templates/index.html`](../src/occams_beard/templates/index.html) uses plain-language symptom choices for self-serve entry and keeps advanced controls behind progressive disclosure.

Verified by unit test:

- [`tests/test_app.py`](../tests/test_app.py) checks for the two entry paths, symptom-led self-serve copy, the guided-support bridge, and the visible support-bundle capture affordance.
- [`tests/test_browser_ui.py`](../tests/test_browser_ui.py) adds opt-in Safari/WebDriver coverage for keyboard entry-path selection, JavaScript symptom auto-loading as a progressive enhancement, native `<details>` behavior, and mode-specific CTA ordering. The test suite skips cleanly when Safari WebDriver is unavailable.

## What remains unverified

Not verified by repository artifacts:

- actual VoiceOver or NVDA spoken output
- manual keyboard behavior in a non-headless desktop browser session on the current host
- Safari/WebKit assistive-technology behavior outside the opt-in WebDriver path
- forced-colors behavior
- reduced-motion behavior
- formal WCAG conformance

Actual screen-reader speech output is not verified by this repository.

## Recommended next audit steps

1. Perform a manual keyboard-only pass in desktop Chrome and Safari against both `/` and `/results/<run_id>`.
2. Run a VoiceOver pass on macOS and record heading, landmark, form-control, and export-flow behavior.
3. If a Windows validation path becomes available, run the same results flow with NVDA and record any divergences.
