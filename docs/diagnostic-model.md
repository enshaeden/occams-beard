# Diagnostic Model

## Design

Occam's Beard follows one shared diagnostics execution flow:

```text
CLI / Web / Launcher / Support Bundle Export
  -> build_run_options
  -> execution plan from registered domains
  -> run context
  -> per-domain collectors
  -> normalized facts
  -> deterministic findings
  -> execution status + deterministic explanation
  -> JSON / report / support bundle / HTML
```

## Model Boundaries

- `run_options.py` validates operator-facing selection into one stable options object.
- `domain_registry.py` defines the registered diagnostic domains, their planned step labels, and the explicit execution order for the shared runner.
- `run_context.py` owns mutable run state: accumulated facts, warnings, durations, completed steps, and live progress emission.
- Collectors gather facts and warnings.
- `models.py` defines normalized facts, findings, execution records, guided summaries, and support-bundle metadata.
- `result_builder.py` assembles the final `EndpointDiagnosticResult` from the completed run context.
- `findings.py` evaluates deterministic rules only from collected evidence.
- `execution.py` turns the completed run into per-domain and per-probe execution status.
- `explanations.py` adds deterministic plain-language guidance on top of findings.
- `serializers.py`, `report.py`, and `support_bundle.py` render the same result object for different consumers.
- `web/` keeps route composition, form parsing, run-session orchestration, progress shaping, and result presentation above the shared result model.

## Execution Model

The shared runner is now intentionally small. It coordinates four responsibilities
without embedding domain-by-domain branching:

1. Build an execution plan from the registered domains selected for the run.
2. Create a run context that owns mutable facts, warnings, timing, and progress.
3. Execute each planned domain through its explicit domain executor.
4. Assemble the final result from the completed context.

This design keeps the orchestration path readable while making it easier to add
or remove domains without rewriting the runner. A new domain now requires a
registered definition with:

- a domain identifier and operator-facing label
- planned step labels for progress accounting
- an explicit executor that calls the collector and updates the run context

The system stays explicit on purpose. Domain executors remain concrete functions
instead of being reduced to a generic plug-in framework. That preserves review
clarity around local evidence collection, warning handling, and inter-domain
dependencies such as routing facts feeding VPN heuristics.

## Current Capabilities

- shared runner for CLI and web
- registry-backed execution plan and run context for domain orchestration
- schema-versioned `result.json`
- execution status values for `passed`, `failed`, `partial`, `unsupported`, `skipped`, and `not_run`
- a dedicated `time` domain for local clock state, timezone facts, and an optional bounded external skew comparison
- additive battery and storage-device health facts under the existing `resources` and `storage` domains
- additive host-pressure snapshot facts under `resources`, including CPU saturation, optional swap or commit pressure, and bounded process-load category summaries when available
- local profile defaults for repeatable issue scenarios
- support-bundle export with optional raw command capture
- standalone support-bundle validation against the current manifest format

## Constraints

- platform parsing stays below findings
- hardware facts stay additive under `resources` and `storage`; there is no new top-level hardware domain
- time facts stay under a dedicated `time` domain so local clock evidence and optional skew egress remain explicit instead of being hidden inside `resources`
- process-level hints remain bounded and snapshot-only; there is no persistent history, full process explorer, or background sampling subsystem
- UI stays above the result model
- explanation stays bounded to evidence already collected
- support artifacts remain local and explicit
- registered domains are composable, but the registry is still local code, not a remote or dynamic plug-in system
- no automatic remediation is introduced
