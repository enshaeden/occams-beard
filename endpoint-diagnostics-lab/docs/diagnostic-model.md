# Diagnostic Model

Endpoint Diagnostics Lab uses a layered collection and normalization model so raw command execution stays separate from reasoning and output.

## Layers

### Collectors

Collectors gather raw facts from the local endpoint. They prefer standard-library APIs first and then use built-in operating system commands where needed.

Current collector domains:
- `system`: hostname, OS, uptime, CPU estimate, memory facts
- `storage`: relevant filesystem usage
- `network`: interface inventory and local addressing
- `routing`: default route and route summary
- `dns`: resolver list and hostname resolution checks
- `connectivity`: TCP reachability, optional ping, optional traceroute
- `vpn`: heuristic tunnel and VPN signals
- `services`: configured host:port checks

Configured targets can be provided directly on the CLI or loaded from a JSON file so repeated private-resource or environment-specific checks remain explicit and portable.

Collectors never format the human report and never infer probable causes directly.

### Models

`models.py` defines the normalized structures used everywhere else in the application. This keeps platform-specific quirks from leaking into findings or output rendering.

Key normalization goals:
- stable field names across platforms
- explicit representation of partial data
- warnings for degraded or unsupported checks
- consistent target, route, interface, and finding shapes

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

### Serializers

`serializers.py` converts normalized result objects into machine-readable JSON suitable for storage, comparison, or later ingestion by external tooling.

### Report

`report.py` renders the human-readable operator view. It is intentionally concise and organized around troubleshooting usefulness rather than exhaustive raw dump formatting.

## Data Flow

```text
CLI
  -> Collectors
  -> Normalized Models
  -> Findings Engine
  -> JSON Serializer / Human Report
```

## Failure Handling

The model treats incomplete data as first-class:
- unsupported checks produce warnings, not crashes
- missing commands produce warnings, not silent skips
- findings require supporting evidence before they trigger
- no baseline check requires elevated privileges

## Traceability

Each execution captures:
- generation timestamp
- selected checks
- platform metadata
- normalized facts
- findings
- warnings

That structure is designed to support repeatable operator workflows and clear audit trails.
