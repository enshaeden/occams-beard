# Architecture Decisions

## Purpose and Scope

Endpoint Diagnostics Lab is intentionally scoped as a local, CLI-first endpoint diagnostics project. The goal is to demonstrate practical systems engineering capability, not to build a remote management platform.

## Major Decisions

### Decision: Keep the runtime dependency set to the Python standard library

Reason:
- favors portability
- keeps the project easy to run on constrained endpoints
- demonstrates disciplined engineering without dependency sprawl

Consequence:
- more text parsing is required for some platform probes
- richer per-platform integrations are intentionally deferred

Dependency note:
- `setuptools` is used as the build backend for editable installs only
- no third-party runtime dependency was introduced

### Decision: Use a strict layered architecture

Layers:
- collectors
- normalized models
- findings engine
- serializers
- human-readable report
- CLI orchestration

Reason:
- keeps reasoning auditable
- keeps output concerns out of collectors
- reduces coupling and improves testability

### Decision: Findings are deterministic and evidence-based

Reason:
- auditability matters more than cleverness for this project
- deterministic rules are easier to review, test, and explain
- the tool should never invent causes unsupported by observed facts

Consequence:
- findings can be conservative
- heuristic conclusions are explicitly labeled

### Decision: No automatic remediation in the first release

Reason:
- automatic system changes would expand risk and scope significantly
- the positioning goal is safe diagnostics and analysis, not remote control

Consequence:
- operator judgment remains in the loop
- rollback stays simple because diagnostics are read-mostly

### Decision: Keep repeated service and connectivity checks file-configurable instead of adding a config service

Reason:
- operators often need stable target sets for private APIs, DNS resolvers, proxies, or known edge services
- a small JSON file keeps that repeatability without introducing a database, daemon, or broader configuration subsystem

Consequence:
- target management stays simple and portable
- richer environment profiles are intentionally deferred

## Security Review

- Inputs from the CLI are validated before use.
- Host:port targets are parsed and range-checked.
- No secrets are logged or required for baseline operation.
- The project avoids shell interpolation and uses argument lists for subprocess execution.
- Command execution is timeout-bounded.

Residual risk:
- debug logging still exposes command names and failure context; operators should treat debug output as operational data.

## Performance Considerations

- The first release uses synchronous collection for clarity and predictability.
- TCP checks are time-bounded and intentionally lightweight.
- The project avoids premature optimization and favors maintainable control flow.

## Rollback Strategy

The implementation is additive and has no schema migrations, agents, installers, or persistent system modifications. Rollback is:

1. revert the introducing commit, or
2. remove the `endpoint-diagnostics-lab/` directory from the repo

No endpoint cleanup is required because the tool does not alter host state.

## Known Tradeoffs

- CPU pressure is estimated rather than sampled through advanced platform counters.
- VPN detection is heuristic and intentionally conservative.
- Windows probe quality depends on broadly available PowerShell behavior.

## Audit and Discovery Log

----------------------------------------
TYPE: Technical debt
SEVERITY: Low

DESCRIPTION:
Sandboxed macOS execution contexts can block or truncate otherwise normal uptime and resolver probes.

IMPACT:
Reports may show warnings and partial metadata for uptime or resolver inventory even when the endpoint itself is healthy.

AFFECTED COMPONENTS:
platform/macos.py
collectors/system.py
collectors/dns.py
docs/platform-notes.md

ROOT CAUSE:
The project intentionally avoids privilege escalation and uses built-in command paths that may still be restricted by the execution environment.

RECOMMENDED RESOLUTION:
Add additional non-privileged fallback probes and expand fixture coverage for sandboxed macOS environments.

STATUS:
UNRESOLVED

IF UNRESOLVED:
- Reason it was not fixed
  The project now emits explicit warnings, but broader fallback coverage needs more environment-specific research and fixtures.
- What is required to resolve later
  Additional macOS capture samples from sandboxed and unrestricted contexts plus fallback probe refinement.
----------------------------------------

----------------------------------------
TYPE: Technical debt
SEVERITY: Low

DESCRIPTION:
Windows probe coverage currently depends on PowerShell output and representative parser assumptions rather than a larger fixture corpus.

IMPACT:
Some Windows variants, especially older or localized hosts, may return partial data or warnings.

AFFECTED COMPONENTS:
platform/windows.py
docs/platform-notes.md

ROOT CAUSE:
The first release intentionally prioritizes standard-library-only runtime behavior and tight scope over broader platform fixture harvesting.

RECOMMENDED RESOLUTION:
Add a larger captured-fixture test matrix for Windows command variants and localized outputs.

STATUS:
UNRESOLVED

IF UNRESOLVED:
- Reason it was not fixed
  Release scope prioritized a clean cross-platform baseline over a wider fixture collection effort.
- What is required to resolve later
  Captured Windows samples from multiple versions and locales plus parser hardening.
----------------------------------------

----------------------------------------
TYPE: Security
SEVERITY: Low

DESCRIPTION:
Command execution could become noisy or risky if shell interpolation or privileged execution were introduced.

IMPACT:
Poor command handling would increase injection and safety risk.

AFFECTED COMPONENTS:
utils/subprocess.py
collectors/*

ROOT CAUSE:
Cross-platform diagnostics often tempt ad hoc shell execution.

RECOMMENDED RESOLUTION:
Use argument-vector subprocess execution, input validation, and bounded timeouts.

STATUS:
RESOLVED
----------------------------------------

----------------------------------------
TYPE: Performance
SEVERITY: Low

DESCRIPTION:
Long-running network probes could degrade operator experience or block automation workflows.

IMPACT:
Slow diagnostics would reduce usability and make the tool harder to embed in operational scripts.

AFFECTED COMPONENTS:
collectors/connectivity.py
utils/subprocess.py

ROOT CAUSE:
Network diagnostics can block on remote timeouts or unavailable commands.

RECOMMENDED RESOLUTION:
Bound probe duration with explicit socket and subprocess timeouts.

STATUS:
RESOLVED
----------------------------------------

----------------------------------------
TYPE: Workflow inefficiency
SEVERITY: Low

DESCRIPTION:
If “not collected” were treated the same as “collected and absent,” partial check runs could trigger misleading findings.

IMPACT:
Operators could receive incorrect fault-domain guidance during selective runs.

AFFECTED COMPONENTS:
cli.py
findings.py

ROOT CAUSE:
Selective diagnostics create ambiguity unless rule evaluation is gated by the enabled domains.

RECOMMENDED RESOLUTION:
Evaluate findings only when the supporting diagnostic domains were explicitly run.

STATUS:
RESOLVED
----------------------------------------
