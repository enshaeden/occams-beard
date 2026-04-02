# Diagnostic Model

Endpoint Diagnostics Lab uses a layered collection and normalization model so raw command execution stays separate from reasoning and output.

## Layers

### Collectors

Collectors gather raw facts from the local endpoint. They prefer standard-library APIs first and then use built-in operating system commands where needed.

Current collector domains:
- `system`: hostname, OS, uptime, CPU estimate, memory facts
- `storage`: relevant filesystem usage
- `network`: interface inventory, local addressing, interface MTU facts, and supplemental ARP or neighbor-cache evidence
- `routing`: default route and route summary
- `dns`: resolver list and hostname resolution checks
- `connectivity`: generic TCP path reachability, optional ping, optional traceroute
- `vpn`: heuristic tunnel and VPN signals
- `services`: configured intended endpoint or application checks

Configured targets can be provided directly on the CLI or loaded from a JSON file so repeated intended service checks remain explicit and portable. The web app prefills the same built-in DNS and TCP targets for the default local workflow, and the CLI still uses those defaults when the operator does not supply overrides.

Some collector heuristics were refined using patterns from an earlier personal troubleshooting script, but the implementation here was rebuilt to fit the project’s structured architecture and evidence model.

Collectors never format the human report and never infer probable causes directly.

### Models

`models.py` defines the normalized structures used everywhere else in the application. This keeps platform-specific quirks from leaking into findings or output rendering.

Key normalization goals:
- stable field names across platforms
- explicit representation of partial data
- warnings for degraded or unsupported checks
- consistent target, route, interface, and finding shapes
- a clear distinction between generic path reachability and intended service reachability
- explicit support for heuristic evidence such as VPN signals and partial traceroute outcomes without collapsing them into hard failure claims

Route normalization is intentionally richer than a binary "default route yes or no" flag. `RouteSummary` keeps route presence, a conservative `default_route_state` (`present`, `missing`, or `suspect`), and human-readable route observations when the raw platform output deserves operator attention.

### Findings

`findings.py` evaluates deterministic rules against normalized facts. Each finding includes:
- identifier
- severity
- title
- summary
- evidence list
- probable cause
- fault domain
- confidence
- heuristic flag where certainty is limited

The findings engine only evaluates rules supported by the checks the operator actually ran. This prevents “not collected” from being misread as “collected and absent.”

The findings model is intentionally evidence-first:
- evidence fields capture observed facts only
- summary captures the derived finding
- heuristic findings are explicitly marked when the probable cause is lower confidence
- partial traceroute and VPN results are treated as supporting evidence, not authoritative proof of a root cause

### Serializers

`serializers.py` converts normalized result objects into machine-readable JSON suitable for storage, comparison, or later ingestion by external tooling.

### Runner

`runner.py` is the shared application service for diagnostics execution. It validates run options, invokes the collectors, assembles normalized facts, evaluates findings, and returns a single result object. Both the CLI and the Flask app call into this layer so the project has one execution path.

### Report

`report.py` renders the human-readable operator view. It is intentionally concise and organized around troubleshooting usefulness rather than exhaustive raw dump formatting.

The report distinguishes:
- observed facts
- derived findings
- heuristic conclusions where certainty is limited

## Data Flow

```text
CLI / Flask App
  -> Runner
  -> Collectors
  -> Normalized Models
  -> Findings Engine
  -> JSON Serializer / Human Report / HTML Templates
```

The interface layers remain intentionally thin:
- the CLI parses `run` options, calls the shared runner, and renders the terminal report
- the Flask app parses form input, calls the shared runner, and renders structured HTML from the result object

## Failure Handling

The model treats incomplete data as first-class:
- unsupported checks produce warnings, not crashes
- missing commands produce warnings, not silent skips
- malformed or partial parser input degrades into warnings or suspect-route observations rather than broken results
- findings require supporting evidence before they trigger
- no baseline check requires elevated privileges
- supplemental ARP evidence is optional and never required for a successful baseline run

## Traceability

Each execution captures:
- generation timestamp
- selected checks
- platform metadata
- normalized facts
- findings
- warnings

That structure is designed to support repeatable operator workflows and clear audit trails.
