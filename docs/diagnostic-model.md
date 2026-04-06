# Diagnostic Model

## Shared Execution Flow

Occam's Beard uses one execution path across CLI, web, launcher, and export surfaces.

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

## Current Model Boundaries

- `run_options.py` validates operator-facing input into one `DiagnosticsRunOptions`
  object.
- `domain_registry.py` defines the registered diagnostic domains, their execution
  order, and progress labels.
- `run_context.py` owns mutable run state: facts, warnings, timings, completed
  steps, and live progress emission.
- Collectors gather facts and warnings.
- `models.py` defines normalized facts, findings, execution records, guided
  summaries, and support-bundle metadata.
- `result_builder.py` assembles the final `EndpointDiagnosticResult`.
- `findings.py` remains the stable findings entrypoint and delegates to focused
  finding modules.
- `execution.py` turns the completed run into per-domain and per-probe execution
  status.
- `explanations.py` adds bounded plain-language guidance from findings,
  execution state, and any captured intake context.
- `serializers.py`, `report.py`, and `support_bundle.py` render the same result
  object for different consumers.
- `web/` keeps route composition, form parsing, session orchestration, progress
  shaping, and result presentation above the shared result model.
- `intake/` owns deterministic symptom-to-intent resolution, clarification, and
  self-serve scope mapping.

## Current Intake Behavior

The intent-driven intake contract is live on the self-serve web path.
`resolve_self_serve_intake_state(...)` in `src/occams_beard/web/forms.py`
resolves the selected symptom, applies any submitted clarification answers,
maps the result to a scoped check set, builds an `IntakeContext`, and passes
that context into `build_run_options(...)` and the result builder.

### Resolver

- `resolve_intake_interpretation(...)` resolves either a canonical symptom id or
  a free-text phrase into one internal intent key.
- Rule order is deterministic and explicit:
  1. exact symptom-id match
  2. exact symptom-phrase match
  3. exact intent-phrase match
  4. token-overlap phrase scoring
  5. unresolved fallback
- Resolver trace metadata records the matched rule, candidate scores, and any
  ranked alternatives for debugging and regression tests.

### Clarification

- `ClarificationEngine` builds a minimal contract-owned question set for the
  resolved intent.
- The current contract caps clarification at one to two prompts per intent.
- The self-serve plan UI renders one unanswered prompt at a time and preserves
  earlier answers in hidden form state.
- Answers refine the active pathway when the result is informative. Otherwise
  the engine either keeps the context unresolved or falls back to the default
  pathway for that intent.

### Mapping And Validation

- `map_intake_to_scope(...)` prefers clarification-selected pathway domains when
  available.
- Without clarification output, mapping falls back to the primary contract
  pathway and then to explicit per-intent default domains.
- Domain selections are converted to checks deterministically.
- Suggested profiles are secondary hints for plan labeling and support handoff;
  they are not the primary self-serve scope control.
- `validate_intake_selected_checks(...)` keeps self-serve operator edits inside
  conservative per-intent bounds before execution starts.

## Current Boundaries

- The self-serve web path is intent-driven.
- `Work With Support` remains profile-driven.
- CLI runs accept explicit operator-selected input and do not prompt for intake
  clarification.
- Clarification, mapping, and validation stay Flask-independent even though the
  current self-serve UI consumes them.
- Explanation can reference captured intake context, but it stays bounded to
  collected evidence and recorded scope metadata.
- There is no probabilistic model, remote policy engine, or open-ended
  questionnaire tree.

## Known Partial Wiring

- The resolver accepts free text, but the main web entrypoint currently submits
  canonical symptom ids rather than exposing a free-text intake field.
- The self-serve plan step shows one outstanding clarification prompt at a time
  even when the contract defines a second follow-up question.
- Support-mode routing still starts from a selected profile and optional bridge
  suggestion instead of reusing the self-serve clarification flow.

## Future Work

- If CLI or support-directed flows adopt the same intake model, route those
  surfaces through the existing `intake/` modules instead of reintroducing
  mapping logic in presentation or Flask route code.
- Keep new phrases, intents, questions, and pathways deterministic, testable,
  and traceable.
- Track priority and sequencing in [`docs/roadmap.md`](roadmap.md) rather than
  expanding this document into a future-state journal.
