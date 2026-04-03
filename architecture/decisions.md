# Architecture Decisions

## Core Decisions

- Keep the runtime standard-library-first except where a clear interface dependency is justified. Flask remains the only runtime dependency.
- Keep collectors, normalized models, findings, execution status, rendering, and interfaces as separate layers.
- Keep findings deterministic and evidence-based.
- Keep the system local-only and read-mostly.
- Keep one shared runner for CLI and web.
- Keep reusable scenarios local and file-backed through profiles instead of a config service.
- Keep support artifacts local and explicit; raw command capture stays opt-in.

## Consequences

- The product stays inspectable and easy to audit.
- CLI and web behavior remain aligned because they share the same execution path.
- New features such as profiles, bundle export, and guided summaries build around the result model instead of bypassing it.
- Privacy and supportability improve without turning the tool into a resident agent or remote platform.

## Non-Goals

- no daemon
- no fleet orchestration
- no cloud upload requirement
- no automatic remediation
- no second frontend stack
