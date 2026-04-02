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

### Decision: Center the public CLI on a single `run` command

Reason:
- endpoint operators should not have to learn a subcommand tree to execute the normal diagnostics workflow
- the CLI should make the default path obvious while keeping orchestration thin and auditable
- one primary command keeps documentation, automation, and support handoffs easier to explain

Consequence:
- `run` is the canonical operator-facing interface for diagnostics execution
- help text, examples, and defaults are optimized around `endpoint-diagnostics-lab run`
- internal parsing and default target selection are handled through small helpers instead of spreading CLI heuristics across the codebase

### Decision: Use one shared diagnostics runner for both CLI and web app interfaces

Reason:
- the project needed a better operator front door without forking the execution model
- diagnostics collection and findings evaluation should remain testable and interface-agnostic
- a thin Flask layer is acceptable only if it stays above the same service used by the CLI

Consequence:
- `runner.py` owns validated execution flow for selected checks and options
- the Flask app renders structured results instead of reusing the terminal report string
- route handlers and CLI commands remain thin wrappers around the same diagnostics core

## Security Review

- Inputs from the CLI are validated before use.
- The local Flask app binds to `127.0.0.1` by default and does not introduce authentication because it is intentionally scoped to single-operator localhost use.
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

----------------------------------------
TYPE: Bug
SEVERITY: Medium

DESCRIPTION:
Repository documentation used absolute local filesystem links, which break GitHub navigation and make the project look unfinished to external reviewers.

IMPACT:
Readers could not reliably navigate from the repository landing page to the active project, docs, or sample artifacts.

AFFECTED COMPONENTS:
README.md
endpoint-diagnostics-lab/README.md

ROOT CAUSE:
Local authoring links were committed instead of repository-relative Markdown links.

RECOMMENDED RESOLUTION:
Replace absolute local paths with repository-relative links and make the active project path explicit from the repository root.

STATUS:
RESOLVED
----------------------------------------

----------------------------------------
TYPE: Workflow inefficiency
SEVERITY: Medium

DESCRIPTION:
The operator report surfaced finding headlines but not enough supporting evidence, and it did not clearly separate direct observations from derived conclusions.

IMPACT:
Reviewers and operators had to infer why a fault domain was chosen, which reduced credibility and auditability.

AFFECTED COMPONENTS:
src/endpoint_diagnostics_lab/report.py
docs/diagnostic-model.md
docs/finding-rules.md
sample_output/

ROOT CAUSE:
The initial report renderer optimized for brevity before adding enough evidence scaffolding.

RECOMMENDED RESOLUTION:
Render concise finding blocks that distinguish observed facts, derived findings, and heuristic conclusions while keeping the output terminal-friendly.

STATUS:
RESOLVED
----------------------------------------

----------------------------------------
TYPE: Workflow inefficiency
SEVERITY: Medium

DESCRIPTION:
Diagnostics execution lived only in the CLI layer, which blocked a proper local app interface and risked duplicating orchestration when a second front end was introduced.

IMPACT:
Adding a better operator-facing interface would have increased drift risk between CLI and web behavior, defaults, and findings output.

AFFECTED COMPONENTS:
src/endpoint_diagnostics_lab/cli.py
src/endpoint_diagnostics_lab/runner.py
src/endpoint_diagnostics_lab/app.py
src/endpoint_diagnostics_lab/templates/
tests/test_runner.py
tests/test_app.py
README.md
docs/diagnostic-model.md

ROOT CAUSE:
The initial project was intentionally CLI-first, so orchestration stayed local to the CLI until a second interface became necessary.

RECOMMENDED RESOLUTION:
Extract a shared diagnostics runner, keep the Flask app thin and local-only, and make both interfaces use the same validated execution path.

STATUS:
RESOLVED
----------------------------------------

----------------------------------------
TYPE: Technical debt
SEVERITY: Medium

DESCRIPTION:
The deterministic findings engine was too narrow for several common endpoint-diagnostics situations such as partial DNS failure, selective filtering, local addressing gaps, and host-pressure interactions.

IMPACT:
The tool could return plausible raw data while still feeling scaffold-like because it failed to synthesize several realistic multi-signal conditions.

AFFECTED COMPONENTS:
src/endpoint_diagnostics_lab/findings.py
tests/test_findings.py
docs/finding-rules.md

ROOT CAUSE:
The first rule set established the pattern correctly but covered only a small number of correlation cases.

RECOMMENDED RESOLUTION:
Add more deterministic multi-signal rules while keeping confidence and heuristic labeling disciplined.

STATUS:
RESOLVED
----------------------------------------

----------------------------------------
TYPE: Technical debt
SEVERITY: Medium

DESCRIPTION:
Platform-specific ping, traceroute, and interface classification behavior relied on assumptions that were too Linux-shaped.

IMPACT:
macOS and Windows behavior could degrade into misleading failures or overly broad interface labeling even when the endpoint state itself was fine.

AFFECTED COMPONENTS:
src/endpoint_diagnostics_lab/collectors/connectivity.py
src/endpoint_diagnostics_lab/collectors/network.py
src/endpoint_diagnostics_lab/utils/parsing.py
docs/platform-notes.md

ROOT CAUSE:
Cross-platform command semantics and naming conventions vary, but the initial collector implementation used simpler shared defaults.

RECOMMENDED RESOLUTION:
Use more deliberate platform-specific argument sets, numeric traceroute output where available, and more conservative interface classification.

STATUS:
RESOLVED
----------------------------------------

----------------------------------------
TYPE: Technical debt
SEVERITY: Low

DESCRIPTION:
Traceroute parsing remains intentionally conservative and is more reliable for numeric IPv4-oriented output than for all possible DNS-labeled or localized variants.

IMPACT:
Some traceroute results may degrade into partial evidence or warnings rather than richly parsed hop metadata.

AFFECTED COMPONENTS:
src/endpoint_diagnostics_lab/utils/parsing.py
docs/platform-notes.md
tests/test_parsing.py

ROOT CAUSE:
The project intentionally avoids deeper protocol parsing and external dependencies in favor of a bounded stdlib-first implementation.

RECOMMENDED RESOLUTION:
Expand captured traceroute fixtures across platforms and add broader parser coverage only if it remains deterministic and maintainable.

STATUS:
UNRESOLVED

IF UNRESOLVED:
- Reason it was not fixed
  This pass tightened invocation and guardrails, but broad traceroute fixture expansion would have increased scope beyond the intended refinement pass.
- What is required to resolve later
  Additional captured traceroute samples from Linux, macOS, and Windows variants plus parser tests for those fixtures.
----------------------------------------

----------------------------------------
TYPE: Workflow inefficiency
SEVERITY: Low

DESCRIPTION:
Sample output artifacts showed JSON only for some scenarios, which made it harder for GitHub reviewers to evaluate the human report without running the tool.

IMPACT:
The project underrepresented its operator-facing output quality during static review.

AFFECTED COMPONENTS:
sample_output/
endpoint-diagnostics-lab/README.md

ROOT CAUSE:
The initial sample artifact set prioritized machine-readable examples before terminal-report examples.

RECOMMENDED RESOLUTION:
Commit representative terminal-style report artifacts alongside scenario JSON samples.

STATUS:
RESOLVED
----------------------------------------

----------------------------------------
TYPE: Workflow inefficiency
SEVERITY: Medium

DESCRIPTION:
The operator-facing CLI exposed `run`, but the public surface still felt like a generic subcommand parser because help text was sparse and the default TCP target behavior was split across layers.

IMPACT:
Operators had to infer the intended execution model, and a no-flag run did not consistently exercise both connectivity and configured service checks with the same default targets.

AFFECTED COMPONENTS:
src/endpoint_diagnostics_lab/cli.py
src/endpoint_diagnostics_lab/defaults.py
src/endpoint_diagnostics_lab/utils/validation.py
src/endpoint_diagnostics_lab/collectors/connectivity.py
README.md
docs/diagnostic-model.md
tests/test_cli.py
tests/test_validation.py

ROOT CAUSE:
The initial implementation added the `run` command correctly but left defaults, help copy, and parser-facing validation distributed across the CLI and collector layers.

RECOMMENDED RESOLUTION:
Centralize shared defaults, keep `run` as the obvious public command, validate selection inputs clearly, and cover the run-first behavior with dedicated CLI tests.

STATUS:
RESOLVED
----------------------------------------
