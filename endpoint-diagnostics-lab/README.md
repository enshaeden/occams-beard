# Endpoint Diagnostics Lab

Endpoint Diagnostics Lab is a CLI-first, cross-platform endpoint diagnostics project built to demonstrate practical systems engineering capability at the host and network layer. It gathers local facts safely, evaluates deterministic findings rules, and produces both a concise operator report and structured JSON output.

This project exists to answer real operator questions without becoming a platform:
- Is the endpoint online and correctly routed?
- Does DNS work?
- Can it reach external services and configured ports?
- Is there evidence of VPN or tunnel state?
- Is the host under resource pressure?
- Based on the observed evidence, what is the most likely failure domain?

It is intentionally not an MDM, not a monitoring SaaS, not a remote control plane, and not an AI-heavy troubleshooting assistant.

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
- `collectors/` gather raw system, network, DNS, connectivity, storage, and service facts
- `models.py` normalizes facts into stable structures
- `findings.py` applies deterministic rules to observed evidence
- `serializers.py` emits machine-readable JSON
- `report.py` renders a concise human-readable report
- `cli.py` orchestrates execution and output behavior

This separation keeps reporting concerns out of collection code and keeps the findings engine free from CLI-specific behavior.

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
├── src/
│   └── endpoint_diagnostics_lab/
├── tests/
├── scripts/
│   └── demo.sh
├── sample_output/
├── pyproject.toml
└── .gitignore
```

## Installation

```bash
cd endpoint-diagnostics-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Runtime dependencies are Python standard library only. `setuptools` is used only as the build backend for editable installs.

## Example Commands

```bash
python -m endpoint_diagnostics_lab.main run
python -m endpoint_diagnostics_lab.main run --json-out report.json
python -m endpoint_diagnostics_lab.main run --checks network,dns,connectivity
python -m endpoint_diagnostics_lab.main run --target github.com:443 --target 1.1.1.1:53
python -m endpoint_diagnostics_lab.main run --target-file sample_output/example-targets.json
python -m endpoint_diagnostics_lab.main run --enable-ping --enable-trace --verbose
```

`--target-file` accepts a JSON array of either `host:port` strings or objects shaped like `{"host": "github.com", "port": 443, "label": "github-https"}` so repeated endpoint and service checks can stay config-driven without introducing a database or service layer.

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

Key Findings
- [INFO] No major diagnostic findings detected: The collected facts did not match any major fault rule.
```

## JSON Output Shape

The JSON output includes:
- metadata
- platform information
- collected facts
- findings
- probable fault domain
- warnings and unsupported checks

Representative samples are committed in [`sample_output/`](/Users/justinsadow/src/occams-beard/endpoint-diagnostics-lab/sample_output).

## Exit Codes

- `0`: diagnostics completed successfully, regardless of whether findings were present
- non-zero: execution or argument failure, such as invalid CLI input or an unhandled runtime error

Findings do not produce non-zero exit codes on their own. This keeps the tool usable in operator workflows where diagnostics should succeed even when the endpoint is degraded.

## Design Tradeoffs

- Standard library only at runtime keeps deployment simple and portable, but some platform probes are more text-parser-heavy than a dependency-backed approach.
- Findings remain deterministic and evidence-based, which improves auditability but intentionally limits speculative guidance.
- The first release prefers bounded local checks over deeper telemetry collection, which keeps the scope disciplined and rollback simple.

## Limitations

- Windows collection relies on PowerShell and common built-in networking tools; localized output and older host variations may require broader fixture coverage.
- VPN detection is heuristic by design and never claims certainty.
- Traceroute and ping coverage depend on command availability and network policy.
- CPU utilization is an estimate, not a profiler-grade measurement.

## Security and Safety

- No automatic remediation actions are performed.
- No privileged operations are required for baseline checks.
- Command execution is bounded with timeouts.
- Logs avoid dumping raw command output unless the operator enables debug logging and even then remain scoped to command invocation context.

## Testing

```bash
cd endpoint-diagnostics-lab
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
```

The test suite focuses on representative parser fixtures, deterministic findings, JSON serialization, report rendering, and network collector normalization without depending on live endpoint state.

## Documentation

- [`docs/problem-statement.md`](/Users/justinsadow/src/occams-beard/endpoint-diagnostics-lab/docs/problem-statement.md)
- [`docs/diagnostic-model.md`](/Users/justinsadow/src/occams-beard/endpoint-diagnostics-lab/docs/diagnostic-model.md)
- [`docs/finding-rules.md`](/Users/justinsadow/src/occams-beard/endpoint-diagnostics-lab/docs/finding-rules.md)
- [`docs/platform-notes.md`](/Users/justinsadow/src/occams-beard/endpoint-diagnostics-lab/docs/platform-notes.md)
- [`docs/roadmap.md`](/Users/justinsadow/src/occams-beard/endpoint-diagnostics-lab/docs/roadmap.md)
- [`architecture/decisions.md`](/Users/justinsadow/src/occams-beard/endpoint-diagnostics-lab/architecture/decisions.md)

## Future Improvements

- Expand platform fixture coverage for Windows and Linux command variations.
- Add richer route interpretation for split-tunnel and policy-route scenarios.
- Add optional artifact bundles for offline troubleshooting handoff.
- Add a constrained integration-test harness for captured sample command output.
