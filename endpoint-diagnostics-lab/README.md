# Endpoint Diagnostics Lab

Endpoint Diagnostics Lab is a CLI-first, cross-platform endpoint diagnostics project built to demonstrate practical systems engineering capability at the host and network layer. It gathers local facts safely, evaluates deterministic findings rules, and produces both a concise operator report and structured JSON output.

The operator-facing interface is centered on a single primary command: `run`.

This project exists to answer real operator questions without becoming a platform:
- Is the endpoint online and correctly routed?
- Does DNS work, partially work, or fail outright?
- Can the host reach generic external paths?
- Can it reach the intended endpoints or services that matter for the operator?
- Is there evidence of VPN or tunnel state?
- Is the host under local resource pressure?
- Based on the observed evidence, what is the most likely fault domain?

It is intentionally not an MDM, not a monitoring SaaS, not a remote control plane, and not an AI-heavy troubleshooting assistant.

## Review Guide

If you are viewing the project on GitHub, the fastest path through the repo is:

1. This README for scope, structure, and usage.
2. [`sample_output/`](sample_output/) for representative JSON and terminal-report artifacts.
3. [`docs/diagnostic-model.md`](docs/diagnostic-model.md) for the normalized collection and reasoning model.
4. [`docs/finding-rules.md`](docs/finding-rules.md) for the deterministic rules and confidence guidance.
5. [`docs/platform-notes.md`](docs/platform-notes.md) for cross-platform tradeoffs and graceful degradation notes.

## What It Proves

For IT, endpoint, infrastructure, and systems engineering roles, this project is designed to show:
- endpoint and OS-level diagnostic fluency
- network troubleshooting judgment
- deterministic reasoning from raw evidence
- disciplined Python engineering with clear layering
- safe, maintainable local tooling that degrades gracefully

## Supported Platforms

- macOS
- Linux
- Windows

Baseline checks do not require sudo or administrator privileges. Some richer checks, such as traceroute visibility or full interface detail, remain subject to platform and command availability.

## Architecture Overview

The codebase uses a deliberately small layered design:
- `collectors/` gather raw system, network, DNS, generic connectivity, storage, service, and VPN facts
- `models.py` normalizes facts into stable structures
- `findings.py` applies deterministic, evidence-based rules
- `serializers.py` emits machine-readable JSON
- `report.py` renders a concise terminal-friendly operator report
- `cli.py` orchestrates execution and output behavior

This separation keeps reporting concerns out of collection code and keeps the findings engine free from CLI-specific behavior.

## Main Command

The normal way to run the tool is:

```bash
endpoint-diagnostics-lab run
```

The module form is equivalent:

```bash
python -m endpoint_diagnostics_lab.main run
```

With no flags, `run` executes the default diagnostic suite, uses built-in DNS and TCP targets, prints the human-readable report, and exits `0` when diagnostics complete even if findings are present.

## Connectivity vs. Service Checks

The project keeps two closely related but distinct concepts:

- `connectivity` means generic path reachability. These checks answer whether the endpoint can get off-box, resolve names, and establish baseline external TCP paths.
- `services` means intended endpoint or application reachability. These checks answer whether the specific destinations the operator cares about are reachable.

The transport may overlap, but the reasoning does not. Findings use generic connectivity to judge broad path health and use service checks to judge target-specific reachability.

## Repository Layout

```text
endpoint-diagnostics-lab/
├── README.md
├── architecture/
│   └── decisions.md
├── docs/
│   ├── problem-statement.md
│   ├── diagnostic-model.md
│   ├── finding-rules.md
│   ├── platform-notes.md
│   └── roadmap.md
├── sample_output/
├── scripts/
│   └── demo.sh
├── src/
│   └── endpoint_diagnostics_lab/
├── tests/
└── pyproject.toml
```

## Installation

```bash
cd endpoint-diagnostics-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Runtime dependencies are Python standard library only. The optional `dev` extras install formatting, linting, and type-check tooling only.

## Example Commands

1. Plain default run

```bash
endpoint-diagnostics-lab run
```

2. Save JSON

```bash
endpoint-diagnostics-lab run --json-out report.json
```

3. Limit checks

```bash
endpoint-diagnostics-lab run --checks network,dns,connectivity
```

4. Add custom targets

```bash
endpoint-diagnostics-lab run --target github.com:443 --target 1.1.1.1:53
```

5. Use a target file

```bash
endpoint-diagnostics-lab run --target-file sample_output/example-targets.json
```

6. Enable ping and trace

```bash
endpoint-diagnostics-lab run --enable-ping --enable-trace --verbose
```

7. Suppress the human-readable report

```bash
endpoint-diagnostics-lab run --suppress-report --json-out report.json
```

The `python -m endpoint_diagnostics_lab.main run ...` form is equivalent for every example above.

`--target-file` accepts a JSON array of either `host:port` strings or objects shaped like `{"host": "github.com", "port": 443, "label": "github-https"}` so repeated service checks can stay config-driven without introducing a database or service layer.

## Run Options

- `--checks`: comma-separated diagnostic domains to run. Supported values are `host`, `resources`, `storage`, `network`, `routing`, `dns`, `connectivity`, `vpn`, and `services`.
- `--json-out`: write structured JSON output to a file.
- `--suppress-report`: skip the human-readable terminal report for machine-oriented workflows.
- `--target`: repeat to add TCP targets as `host:port`.
- `--target-file`: load TCP targets from a JSON array of `host:port` strings or `{host, port, label}` objects.
- `--dns-host`: repeat to add DNS resolution hostnames.
- `--enable-ping`: add best-effort ping checks.
- `--enable-trace`: add best-effort traceroute or tracert checks.
- `--verbose`: enable INFO-level logging.
- `--debug`: enable DEBUG-level logging.

## Example Human-Readable Output

```text
Endpoint Diagnostics Lab Report
================================

Summary
- Host: workstation-01
- Platform: Linux 6.8.0 (x86_64)
- Internet reachable: yes
- Default route present: yes
- Probable fault domain: healthy
- Fault-domain basis: No major diagnostic findings detected (0.80 confidence)

Key Findings
1. [INFO] No major diagnostic findings detected
   Derived finding: The collected facts did not match any enabled fault rule.
   Observed fact: Deterministic rule evaluation completed without triggering supported fault signatures.
   Probable cause: No major failure domain was identified from the collected evidence.
   Fault domain: healthy (0.80 confidence, evidence-based)
```

The report intentionally distinguishes between:
- observed facts
- derived findings
- heuristic conclusions where certainty is limited

## JSON Output Shape

The JSON output includes:
- metadata
- platform information
- collected facts
- findings
- probable fault domain
- warnings and degraded checks

Representative samples are committed in [`sample_output/`](sample_output/), including both machine-readable JSON and terminal-style report artifacts for healthy, DNS-failure, no-route, resource-pressure, and VPN-heuristic scenarios.

## Exit Codes

- `0`: diagnostics completed successfully, regardless of whether findings were present
- non-zero: execution or argument failure, such as invalid CLI input or an unhandled runtime error

Findings do not produce non-zero exit codes on their own. This keeps the tool usable in operator workflows where diagnostics should succeed even when the endpoint is degraded.

## Tooling and Verification

```bash
cd endpoint-diagnostics-lab
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m black --check src tests
python3 -m ruff check src tests
python3 -m mypy src
```

The test suite focuses on representative parser fixtures, deterministic findings, JSON serialization, report rendering, and collector normalization without depending on live endpoint state.

## Design Tradeoffs

- Standard library only at runtime keeps deployment simple and portable, but some platform probes remain more text-parser-heavy than a dependency-backed approach.
- Findings remain deterministic and evidence-based, which improves auditability but intentionally limits speculative guidance.
- The report stays concise for terminal use, so it emphasizes the strongest findings and supporting evidence rather than dumping every raw fact.
- The first release prefers bounded local checks over deeper telemetry collection, which keeps the scope disciplined and rollback simple.

## Limitations

- Windows collection relies on PowerShell and common built-in networking tools; localized output and older host variations still need broader fixture coverage.
- VPN detection is heuristic by design and never claims certainty.
- Traceroute and ping coverage depend on command availability and network policy.
- CPU utilization is an estimate, not a profiler-grade measurement.
- Traceroute parsing is intentionally conservative and is more reliable with numeric hop output than with arbitrary DNS-resolved labels.

## Security and Safety

- No automatic remediation actions are performed.
- No privileged operations are required for baseline checks.
- Command execution is bounded with timeouts.
- CLI inputs are validated before use.
- Logs avoid dumping raw command output unless the operator enables debug logging and even then remain scoped to command invocation context.

## Documentation

- [`docs/problem-statement.md`](docs/problem-statement.md)
- [`docs/diagnostic-model.md`](docs/diagnostic-model.md)
- [`docs/finding-rules.md`](docs/finding-rules.md)
- [`docs/platform-notes.md`](docs/platform-notes.md)
- [`docs/roadmap.md`](docs/roadmap.md)
- [`architecture/decisions.md`](architecture/decisions.md)

## Future Improvements

Future improvements are intentionally documented rather than folded into this pass when they would expand scope more than diagnostic credibility:

- broaden parser fixture coverage for more Windows and Linux variants
- improve route interpretation for split-tunnel and policy-route cases
- add optional raw-command fixture packs for integration-style parser testing
- add constrained proxy and captive-portal visibility checks only if they can remain deterministic and local
