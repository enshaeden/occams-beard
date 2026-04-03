# Architecture Decisions

## Core Decisions

- Keep the runtime standard-library-first except where a clear interface dependency is justified. Flask remains the only runtime dependency.
- Keep collectors, normalized models, findings, execution status, rendering, and interfaces as separate layers.
- Keep findings deterministic and evidence-based.
- Keep the explanation layer bounded to translating deterministic findings into human guidance; it is not a general assistant surface.
- Keep the system local-only and read-mostly.
- Keep one shared runner for CLI and web.
- Keep reusable scenarios local and file-backed through profiles instead of a config service.
- Keep support-ready bundle export and validation as a defined core surface; raw command capture stays opt-in.
- Keep the local web layer thin by separating route composition, form parsing, run-session orchestration, progress shaping, and result presentation.

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
- no generalized conversational assistant
