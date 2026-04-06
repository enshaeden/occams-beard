# Roadmap

This document tracks future work and blockers. Current architecture and runtime
behavior belong in [`docs/diagnostic-model.md`](diagnostic-model.md),
[`docs/support-workflow.md`](support-workflow.md), and
[`architecture/decisions.md`](../architecture/decisions.md).

## Current Blockers

- Fixture coverage is stronger, but it still does not represent every platform,
  OS version, and localization variant that the collectors may encounter.
- Repository accessibility artifacts cover semantics, focus states, and limited
  browser behavior, but real assistive-technology validation is still missing.
- Live smoke validation covers GitHub-hosted Ubuntu, macOS, and Windows
  runners, but it does not yet represent every enterprise image, self-hosted
  runner baseline, or non-English local runtime.
- Support-bundle trust is stronger with the validator, but hostname redaction
  still depends on deterministic known-value registration and broader edge-case
  coverage.
- Non-privileged storage-device health coverage remains thin on Linux and still
  depends on what the host exposes on macOS and Windows.

## Next Milestones

1. Run manual assistive-technology validation in desktop Chrome and Safari with
   VoiceOver, and add Windows NVDA validation if a Windows desktop path is
   available.
2. Add more reviewed fixtures from non-English Windows and Linux hosts plus
   additional macOS resolver, routing, and hardware-output variants collected
   from real systems.
3. Use the bundle validator in release preparation and strengthen automated
   redaction-verification coverage around remaining hostname and mixed-text edge
   cases.

## Intake Follow-Up

- Decide whether the intent-driven self-serve intake flow should also become the
  default intake model for CLI or support-directed runs.
- If that work is taken on, keep the existing `intake/` contract as the single
  source of truth instead of duplicating mapping rules in route or presentation
  layers.

## Explicitly Out Of Scope

- persistent management systems
- RMM or fleet-control behavior
- remote agent platforms
- control-plane behavior
- background agents
- dashboards
- mandatory cloud services
- automatic remediation
