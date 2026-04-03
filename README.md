# Occam's Beard

## What this is

Occam's Beard is a local operator tool for host and network diagnostics. It collects bounded endpoint evidence, normalizes that evidence into a stable model, evaluates deterministic findings, and exposes the same diagnostics run through a CLI and a local web app backed by a shared runner.

## Problem space

Endpoint issues are often triaged with ad hoc commands, screenshots, and incomplete handoffs. That makes it hard to answer basic operational questions consistently: whether the host is healthy enough to continue, whether DNS is implicated, whether general network egress works, whether intended services are reachable, and which fault domain the collected evidence supports.

## Design approach

The system is local-only and read-mostly. It does not rely on agents, remote services, persistent state, or automatic remediation. Collection is organized by diagnostic domain, platform-specific details are normalized before reasoning, and findings are generated only from evidence that was actually collected during the run.

Connectivity checks and service checks are kept separate on purpose:

- `connectivity` checks establish generic path health, such as DNS resolution and baseline external TCP reachability.
- `services` checks evaluate intended destinations using the same transport primitives but a different reasoning path.

Both interfaces call the same runner, so the CLI and the web app execute the same checks, defaults, validations, and findings logic.

## Key capabilities

- Collect host, resource, storage, network, routing, DNS, connectivity, VPN, and service state from the local endpoint
- Normalize cross-platform command output into stable models before evaluation
- Produce deterministic findings with explicit evidence, fault domain, confidence, and heuristic labeling
- Render a concise terminal report and machine-readable JSON from the same result object
- Run the same diagnostics flow through the CLI or a localhost web interface

## Architecture

The repository uses a small layered structure:

- `collectors/` gathers raw host and network evidence
- `models.py` defines normalized result shapes
- `findings.py` maps collected evidence to deterministic findings
- `runner.py` validates run options and executes the shared diagnostics flow
- `serializers.py`, `report.py`, and the web templates render the result for different consumers
- `cli.py` and `app.py` are thin interface layers over the same runner

This boundary keeps platform parsing out of the findings engine, keeps UI concerns out of collection code, and avoids interface drift between the CLI and the web app.

Repository layout:

```text
occams-beard/
├── README.md
├── architecture/
│   └── decisions.md
├── docs/
│   ├── diagnostic-model.md
│   ├── finding-rules.md
│   ├── platform-notes.md
│   ├── problem-statement.md
│   └── roadmap.md
├── sample_output/
├── scripts/
├── src/
│   └── occams_beard/
├── tests/
└── pyproject.toml
```

## Usage

Installation:

```bash
cd occams-beard
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Reviewer entry points:

1. Read this file for scope and interface boundaries.
2. Read [`docs/problem-statement.md`](docs/problem-statement.md) for the operational problem.
3. Read [`docs/diagnostic-model.md`](docs/diagnostic-model.md) for the shared model and runner flow.
4. Read [`docs/finding-rules.md`](docs/finding-rules.md) for the reasoning boundary.
5. Read [`docs/platform-notes.md`](docs/platform-notes.md) for platform assumptions and degradation behavior.
6. Read [`architecture/decisions.md`](architecture/decisions.md) for the architecture rationale.
7. Read [`sample_output/README.md`](sample_output/README.md) and the artifacts in [`sample_output/`](sample_output/) for representative output.

Run the default diagnostic suite:

```bash
occams-beard run
```

Save JSON:

```bash
occams-beard run --json-out report.json
```

Limit the run to selected domains:

```bash
occams-beard run --checks network,dns,connectivity
```

Override the default TCP targets:

```bash
occams-beard run --target github.com:443 --target 1.1.1.1:53
```

Load TCP targets from a JSON file:

```bash
occams-beard run --target-file sample_output/example-targets.json
```

Enable optional ping and traceroute collection:

```bash
occams-beard run --enable-ping --enable-trace --verbose
```

Run the local web app:

```bash
occams-beard-web
```

Or run the Python module directly:

```bash
python -m occams_beard.app
```

Start the local operator launcher, which selects a localhost port and opens the browser:

```bash
occams-beard-operator
```

On macOS, the Finder-friendly launcher is [`scripts/open-operator-interface.command`](scripts/open-operator-interface.command).

The default web bind address is `127.0.0.1:5000`. Results are stored in memory for the local session and can be downloaded as JSON. Representative JSON and terminal report artifacts are committed in [`sample_output/`](sample_output/).

## Tradeoffs and limitations

- The tool is local-only. It is not a remote control plane, agent framework, monitoring service, or remediation system.
- The web app is designed for single-operator localhost use and does not implement authentication, persistence, or multi-user workflows.
- Baseline checks do not require elevated privileges, so some platform details remain partial when the operating system withholds command output.
- VPN detection is heuristic. Tunnel-like interfaces and route hints are evidence, not proof of an active or correctly routed VPN session.
- Ping and traceroute are optional and best-effort. Command availability, network policy, and platform-specific flags affect what can be collected.
- Windows collection depends on common PowerShell and built-in networking tools. Older or localized output variants may degrade into warnings or partial results.
- CPU pressure is an estimate intended for troubleshooting context, not detailed performance analysis.

## Future work

- Expand parser fixture coverage for additional Windows, Linux, and traceroute variants
- Improve route interpretation for split-tunnel and policy-route cases
- Add optional raw command capture for offline review bundles
- Add a clearer summary of degraded versus unsupported checks
