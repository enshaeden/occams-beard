# Roadmap

## What this is

This document records the current release boundary for Occam's Beard and the next changes that fit that boundary.

## Problem space

Diagnostics tools tend to accumulate adjacent features quickly: persistence, remote orchestration, dashboards, policy layers, and remediation. Without an explicit roadmap, that expansion obscures the actual operating model of the system.

## Design approach

The roadmap keeps the project narrow. Near-term work should improve evidence quality, parser coverage, and operator clarity without changing the local, deterministic, read-mostly nature of the tool.

## Key capabilities

Current release focus in `0.1.0`:

- local CLI execution
- local web execution backed by the same runner
- structured diagnostics collection
- deterministic findings
- JSON output and terminal reporting
- representative tests, documentation, and sample artifacts

## Architecture

The roadmap follows the existing architecture rather than introducing a second system. Planned work stays inside the current boundaries:

- better fixture coverage and parser hardening
- more precise routing and tunnel interpretation
- clearer handling of degraded versus unsupported checks
- optional local artifacts that support offline review without adding a control plane

## Usage

Use this document to understand what changes fit the current scope before proposing new work. For the current system behavior, start with [`README.md`](../README.md). For the reasoning and platform boundaries, continue with [`docs/diagnostic-model.md`](diagnostic-model.md), [`docs/finding-rules.md`](finding-rules.md), and [`docs/platform-notes.md`](platform-notes.md).

## Tradeoffs and limitations

- The roadmap does not include agents, daemons, dashboards, remote orchestration, centralized storage, or automatic remediation.
- Configuration remains intentionally small and local.
- Improvements are prioritized when they strengthen evidence quality or operator clarity rather than broaden product surface area.

## Future work

Near term:

- broaden parser fixture coverage for additional platform variants
- improve routing interpretation for split-tunnel and policy-route cases
- add optional raw command capture for offline troubleshooting bundles
- improve summaries for degraded versus unsupported checks

Later, if the same operating model can be preserved:

- add importable fixture packs for integration-style parser tests
- add constrained proxy and captive-portal visibility checks
- support optional configuration files for repeatable service-target bundles
