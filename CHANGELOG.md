# Changelog

## Unreleased

### Added

- Schema-versioned result output with execution-status records.
- Shared Python bootstrap for the repo-root operator launcher plus a Windows `Open Device Check.cmd` shim, so the local operator UI can be launched from the repo root on both macOS and Windows.
- Narrow hardware-health facts under the existing `resources` and `storage` domains, starting with read-only battery state and storage-device health where the OS exposes it without elevation.
- Local profile/scenario support for common troubleshooting issue types.
- Support-bundle export with manifest, redaction report, and optional raw command capture.
- Standalone support-bundle validation for directory and zip exports.
- Guided self-service explanation layer for CLI and web results.
- Privacy and profile format documentation.
- CI workflow and contribution guidance.
- Documentation governance checks with blocking CI enforcement.
- Accessibility notes for verified UI work and remaining manual validation gaps.
- Deterministic sample artifact generation and golden-style regression coverage for committed review artifacts.
- Broader parser and VPN fixture coverage for split-tunnel, resolver, routing, and traceroute variance.
- Additional parser fixtures for macOS split-tunnel routes and utun interfaces, Linux blackhole/default-route and IPv6 resolver variants, and Windows tunnel, malformed route-print, and complete tracert variants.
- Additional parser fixtures for legacy Linux `netstat -rn`, macOS `scutil --dns`, Windows DNS server enumeration, and Windows route-print output with localized section headers.
- Optional browser-level UI coverage for key localhost flows.
- Bounded live smoke validation for the shared runner on GitHub-hosted Ubuntu, macOS, and Windows runners, with a non-sensitive smoke summary artifact.

### Changed

- The repo-root launcher now rejects an existing `.venv` interpreter when it is older than the supported Python baseline, so stale local virtualenv state does not block the macOS `.command` launcher before browser open.
- The shared operator launcher now keeps `webbrowser.open(..., new=2)` as the primary browser path but falls back to the OS-native default URL launcher on Windows, macOS, and Linux when Python browser dispatch is unavailable or rejected, including cold-start cases where no browser process is already running.
- Windows host/resource collection now avoids privileged CIM for uptime, memory, and basic battery facts, suppresses the non-actionable `load-average-unsupported` warning on Windows, and falls back to `ipconfig /all` when PowerShell DNS enumeration is denied.
- The launcher now detects an occupied preferred localhost port, reports the conflicting runtime when possible, falls back to a new port instead of silently reusing the old server, and the UI now exposes runtime metadata plus a `/health/runtime` endpoint.
- The local web interface is now split into focused `web/` modules for route composition, form parsing, session orchestration, progress shaping, and result presentation so the shared runner remains the architectural center.
- The deterministic explanation layer now lives under `explanations.py`, with `assistant.py` retained only as a compatibility facade.
- Core documentation, UI copy, and architecture notes now define Occam's Beard explicitly as a local-first troubleshooting assistant with deterministic diagnostics and support-ready export, with stronger non-goals around fleet, management, and generalized assistant behavior.
- Support-bundle export is now documented more explicitly as a core local handoff surface rather than an incidental download path.
- The localhost web app now starts with two clear paths: `Check My Device` and `Work With Support`.
- Hostname resolution in DNS checks and trace-target preparation is now time-bounded and reported as partial instead of blocking the whole run.
- The self-serve web path now works without JavaScript, with JavaScript limited to auto-loading the recommended plan as a progressive enhancement.
- Support-bundle redaction now applies a generic IPv4 and IPv6 text sweep after exact-value registration.
- Invalid optional local profile files are now skipped and surfaced in the CLI profile listing and support-path profile picker instead of breaking catalog loading.
- Result rendering now includes additive battery and storage-device health summaries when those domains are selected.
- Result rendering now separates evidence-based conclusions, heuristic guidance, and uncertainty.
- JSON serialization now emits `schema_version` and omits raw command capture from `result.json`.
- Root documentation is now limited to `README.md`, `CHANGELOG.md`, and `CONTRIBUTING.md`.
- The support workflow moved to [`docs/support-workflow.md`](docs/support-workflow.md), and one-off planning docs were absorbed into the canonical docs.
- Static analysis is now fully blocking in CI, including `E501` line-length enforcement.
- Committed sample artifacts now reflect the current schema `1.1.0`, execution-status output, guided summaries, and support-bundle format.
- The server-rendered Flask UI now includes accessibility-focused hardening for labels, focus states, skip navigation, export affordances, error semantics, and human-readable domain-checkbox labels.
- Repository docs now remove the transient next-stage assessment after its durable content was absorbed into canonical docs.
- Static-analysis scope now lives in the canonical development docs instead of a separate status file.
- Profile-override and sample-artifact guidance now live in [`docs/profile-format.md`](docs/profile-format.md) and [`docs/result-schema.md`](docs/result-schema.md) instead of folder-local READMEs.
- Profile-listing docs and CLI help now describe the combined built-in plus local profile catalog.
- Windows resolver enumeration now includes multi-family DNS server output, and Windows route-print parsing no longer depends on English section headers.
