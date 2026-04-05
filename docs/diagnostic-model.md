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
- `findings.py` stays the stable findings entrypoint and delegates to explicit
  concern-focused rule modules only from collected evidence.
- `execution.py` turns the completed run into per-domain and per-probe execution status.
- `explanations.py` adds deterministic plain-language guidance on top of findings, execution state, and intake context (reported symptom, resolved intent, and scope rationale).
- `serializers.py`, `report.py`, and `support_bundle.py` render the same result object for different consumers.
- `web/` keeps route composition, form parsing, run-session orchestration, progress shaping, and result presentation above the shared result model.
- `intake/` centralizes intent-driven translation from user-selected symptom language into deterministic execution scope, clarification pathways, and support-path suggestions.


## Intake Resolver Layer (Phase 1)

The intake package now includes a standalone deterministic resolver in
`src/occams_beard/intake/resolver.py`.

Resolver contract output:

- `primary_intent`: internal intent key or `None` when unresolved
- `confidence_score`: bounded deterministic score from `0.0` to `1.0`
- `alternative_intents`: ranked alternatives for ambiguity handling
- `trace`: rule and candidate metadata for debugging and automated tests

Current deterministic rule order:

1. Exact symptom-id match from the canonical contract (`1.0` confidence).
2. Exact phrase match from symptom labels/phrases and intent phrases.
3. Token-overlap phrase matching for free-text input.
4. Unknown fallback with unresolved intent and `0.0` confidence.

Extension rules:

- Keep all resolver behavior deterministic and explainable.
- Add or adjust phrases in `intake/catalog.py` first; avoid duplicating mapping
  logic in `web/forms.py` or presentation modules.
- Prefer adding explicit phrase rules and tests over speculative NLP/statistical
  scoring.
- Preserve stable trace metadata keys so downstream clarification and mapping
  phases can rely on resolver outputs.

## Clarification Engine Layer (Phase 2)

A standalone clarification engine now lives in `src/occams_beard/intake/clarification.py` with typed refinement models in `src/occams_beard/intake/clarification_models.py`.

Clarification contract output:

- `questions`: minimal per-intent prompt set (capped at 1-2 prompts)
- `context`: deterministic decision state with:
  - active intent
  - answered and remaining clarification keys
  - candidate pathways
  - selected pathway (when resolved)
  - downstream domain hints and profile fallback
  - machine-readable status and reason codes

Refinement behavior:

1. Build initial question set directly from the canonical intake contract.
2. Validate answer options against the selected question contract.
3. Deterministically score pathway candidates from answer/pathway token overlap.
4. Resolve to a pathway when possible, or remain unresolved until fallback is required.

Design constraints for this phase:

- Clarification logic remains Flask-independent and route-agnostic.
- `web/forms.py` can consume clarification context later without rewriting current one-step submit flow yet.
- No branching questionnaire tree is introduced beyond the contract-owned 1-2 clarification prompts per intent.

## Domain Mapper Layer (Phase 3)

Self-serve intake scope now runs through `src/occams_beard/intake/domain_mapper.py`.

Mapper contract output:

- `selected_checks`: the execution checks to run for the self-serve path
- `suggested_profile_id`: optional profile used only as a secondary artifact (defaults, bridge context, guidance labels)
- `fallback_mode`: optional marker when intent resolution or refined domains cannot be mapped directly

Current mapping behavior:

1. Resolve intake intent from symptom/free-text via `intake/resolver.py`.
2. Prefer clarification-refined domains (`DecisionContext.next_domains`) when available.
3. Otherwise use intent baseline domains from the intake contract/pathways.
4. Convert domains to checks deterministically.
5. Fall back to general/custom scope when mapping is unresolved.

Design constraints for this phase:

- Self-serve execution scope is intent/domain driven first, with profiles retained as secondary hints.
- Support mode remains profile-driven.
- `build_run_options(...)` stays unchanged, consuming checks/targets/dns passed by web form state.

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
- explanation stays bounded to evidence already collected and intake scope metadata already captured during run setup
- support artifacts remain local and explicit
- registered domains are composable, but the registry is still local code, not a remote or dynamic plug-in system
- no automatic remediation is introduced

## Intake Contract Direction (Phase 0)

A new canonical intake package now defines symptom-to-intent mapping independently from
web presentation metadata: `src/occams_beard/intake/`.

The intake contract is now the source of truth for:

- constrained internal intent taxonomy (7 intents)
- user-facing symptom entry keys and representative phrases
- clarification questions used for intent refinement
- refined answer pathways
- downstream domain/check mappings and profile fallback presets

This is intentionally additive in Phase 0. Runtime orchestration and web form wiring stay
unchanged until later phases consume the intake contract directly.
