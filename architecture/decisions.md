# Architecture Decisions

## Core Decisions

- Keep the runtime standard-library-first except where a clear interface dependency is justified. Flask remains the only runtime dependency.
- Keep collectors, normalized models, findings, execution status, rendering, and interfaces as separate layers.
- Keep domain orchestration explicit through a local domain registry, an execution plan, and a mutable run context instead of a hand-stitched runner.
- Keep findings deterministic and evidence-based.
- Keep the explanation layer bounded to translating deterministic findings into human guidance; it is not a general assistant surface.
- Keep the system local-only and read-mostly.
- Keep one shared runner for CLI and web.
- Keep reusable scenarios local and file-backed through profiles instead of a config service.
- Keep support-ready bundle export and validation as a defined core surface; raw command capture stays opt-in.
- Keep the local web layer thin by separating route composition, form parsing, run-session orchestration, progress shaping, and result presentation.
- Keep symptom-to-execution translation in a dedicated intake layer so UI wording can evolve without scattering profile mapping logic across route and form modules.

## Consequences

- The product stays inspectable and easy to audit.
- CLI and web behavior remain aligned because they share the same execution path.
- Adding a new diagnostic domain now means registering one explicit domain definition rather than editing the runner's sequencing, timing, progress, and warning logic in multiple places.
- Progress accounting, duration tracking, warning accumulation, fact aggregation, and final result assembly now have clearer ownership boundaries.
- New features such as profiles, bundle export, and guided summaries build around the result model instead of bypassing it.
- Privacy and supportability improve without turning the tool into a resident agent or remote platform.

## Tradeoffs Accepted

- The registry is intentionally code-defined and static. This is a maintainability choice, not a move toward a dynamic plug-in platform.
- Per-domain executors remain explicit functions even though they share a common run context. This avoids hiding local collection behavior behind a generic abstraction that would be harder to review.
- Operator-facing execution records still render in the stable domain order used elsewhere in the product, even though the execution plan now owns run sequencing.

## Non-Goals

- no daemon
- no fleet orchestration
- no cloud upload requirement
- no automatic remediation
- no second frontend stack
- no generalized conversational assistant

## Intake Architecture Direction

- Adopt an intent-driven intake control plane as a canonical internal contract under
  `src/occams_beard/intake/`.
- Keep user-facing symptom labels as presentation concerns, but map them through an
  internal intent taxonomy before selecting clarification and execution pathways.
- Keep profiles as fallback execution presets, not the primary intake abstraction.

### Consequences

- Symptom -> intent -> clarification -> pathway -> domains mapping is centralized and testable.
- Runtime and route rewiring can happen incrementally while preserving existing behavior.
- Future intake extensions can be reviewed in one contract location rather than spread across
  web presentation and route code.
