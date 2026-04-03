# Architecture Decisions

## What this is

This document records the architectural decisions that define how Occam's Beard is built and why those boundaries are kept narrow.

## Problem space

A local diagnostics tool needs to be portable, reviewable, and predictable. If collection, inference, and presentation are coupled together, the resulting system becomes harder to test, harder to audit, and easier to overstate.

## Design approach

The project favors a small dependency set, explicit interfaces, deterministic findings, and a shared execution path. The core decisions are:

- keep the runtime dependency set close to the Python standard library
- separate collectors, normalized models, findings, rendering, and interface code
- treat findings as deterministic and evidence-based
- keep the system local-only and read-mostly
- use one shared runner for both the CLI and the web app
- keep repeated targets file-configurable rather than introducing a configuration service
- keep the public CLI centered on a single `run` workflow
- provide a dedicated local launcher without turning the system into a resident service

These decisions keep the project inspectable, testable, and clearly bounded as a local diagnostics tool.

## Key capabilities

- One diagnostics runner for both interfaces
- Deterministic findings tied to collected evidence
- File-based target configuration for repeatable service checks
- Local operator workflows through CLI, web app, and launcher
- Explicit warnings for degraded or unsupported collection

## Architecture

Runtime boundaries:

- `collectors/` gathers platform-specific evidence
- `models.py` defines stable normalized shapes
- `findings.py` applies deterministic rules to normalized facts
- `runner.py` validates inputs and orchestrates the shared execution flow
- `serializers.py`, `report.py`, and the web templates render the result without changing the evidence model
- `cli.py`, `app.py`, and `launcher.py` stay thin and interface-focused

Decision consequences:

- a stdlib-first runtime reduces dependency sprawl but requires more careful parsing of built-in command output
- deterministic findings are easier to audit but intentionally conservative
- local-only operation removes remote control concerns but also excludes persistence, fleet workflows, and centralized history
- a shared runner prevents interface drift but keeps both interfaces within the same execution constraints
- synchronous collection keeps timeout behavior explicit and predictable at the cost of some throughput

## Usage

Read this file after the main README and the diagnostic model. It is the architecture entry point for reviewers who want the rationale before reading implementation details.

Suggested order:

1. [`README.md`](../README.md)
2. [`docs/diagnostic-model.md`](../docs/diagnostic-model.md)
3. [`docs/finding-rules.md`](../docs/finding-rules.md)
4. [`docs/platform-notes.md`](../docs/platform-notes.md)
5. this file

## Tradeoffs and limitations

- The local web app binds to `127.0.0.1` by default and does not implement authentication because it is scoped to single-operator localhost use.
- Debug logging can still expose command names and failure context, so it should be treated as operational data.
- CPU pressure remains an estimate rather than a high-resolution performance signal.
- VPN detection remains heuristic and conservative.
- Windows behavior depends on common PowerShell and built-in command availability.
- Traceroute parsing is intentionally conservative and remains stronger for common numeric output than for every localized variant.

## Future work

- Add broader fixture coverage for Windows and traceroute variants
- Refine split-tunnel and policy-route interpretation without weakening determinism
- Add more non-privileged fallback probes for restricted execution contexts
