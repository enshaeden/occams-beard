# Roadmap

## Target Product

Occam's Beard is a local-first troubleshooting assistant with deterministic diagnostics and support-ready export. It safely collects local diagnostic evidence, interprets it deterministically, explains likely fault domains in plain language, guides the user through safe next steps, and produces support-ready artifacts without requiring a cloud dependency.

## Product Boundaries

The operating model remains:

- local-first
- read-mostly diagnostics
- deterministic findings
- one shared runner
- bounded explanation layer
- support-ready bundle export and validation
- no background agent
- no cloud dependency by default
- no automatic remediation

## Solid Today

- shared runner behavior across CLI, web, and launcher
- deterministic findings over normalized models
- bounded subprocess and hostname-resolution execution with explicit warning and execution-status reporting
- schema-versioned result output and local support-bundle export
- additive hardware-health facts under the existing `resources` and `storage` domains
- local profiles, guided self-service summaries, and support-ready artifacts
- no-JavaScript self-serve symptom selection fallback, with JavaScript limited to progressive enhancement
- optional local profile overrides that are skipped cleanly when malformed while built-ins stay strict
- standalone support-bundle validation for directory and zip exports
- CI gates for documentation structure, unit tests, `ruff` including `E501`, `mypy`, and bounded live smoke validation on GitHub-hosted Ubuntu, macOS, and Windows runners
- canonical committed sample artifacts that match schema `1.3.0` and current support-bundle output
- broader parser coverage for Linux, macOS, and Windows split-tunnel, resolver, VPN, malformed-route, legacy-netstat, localized route-print, and traceroute/routing variants
- documented accessibility hardening in the existing server-rendered UI, plus optional browser-level coverage for key flows

## Current Adoption Blockers

- fixture coverage is stronger, but still not broad enough to represent every platform, OS version, and localization variant
- repository artifacts cover semantics, focus states, and limited browser behavior, but real assistive-technology validation is still missing
- live smoke validation now covers GitHub-hosted runner images, but it does not yet represent every enterprise endpoint build or non-English local runtime
- support-bundle trust is better with the validator, but hostname redaction still depends on deterministic known-value registration
- non-privileged storage-device health coverage is still thin on Linux and depends on what the host exposes on macOS and Windows

## Next 3 Milestones

1. Run manual assistive-technology validation in desktop Chrome and Safari with VoiceOver, and add Windows NVDA validation if a Windows desktop path is available.
2. Add more reviewed fixtures from non-English Windows and Linux hosts plus additional macOS resolver, routing, and hardware-output variants collected from real systems.
3. Use the bundle validator in release prep and strengthen automated redaction-verification coverage around remaining hostname and mixed-text edge cases.

## Explicitly Out of Scope

- persistent management systems
- RMM or fleet-control behavior
- remote agent platforms
- control-plane behavior
- background agents
- dashboards
- mandatory cloud services
- automatic remediation
