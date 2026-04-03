# Diagnostic Model

## What this is

This document describes the collection, normalization, and execution model used by Occam's Beard.

## Problem space

Host and network diagnostics become harder to audit when platform-specific command output, inferred conclusions, and presentation logic are mixed together. That also increases the risk of overstating what the evidence supports.

## Design approach

Occam's Beard separates raw collection, normalized facts, deterministic findings, and rendering. The runner validates operator input, executes the selected domains, assembles a single result object, and passes that result to the CLI and the web app. Findings only evaluate against domains that were actually collected.

Connectivity and service checks are intentionally distinct:

- `connectivity` evaluates generic path health through DNS, external TCP reachability, and optional ping or traceroute.
- `services` evaluates intended destinations using configured targets and separate findings rules.

The transport may overlap. The interpretation does not.

## Key capabilities

- Cross-platform collection domains with explicit warnings for degraded or unsupported checks
- Stable normalized models for routes, interfaces, targets, findings, and warnings
- Deterministic findings with evidence, severity, confidence, fault domain, and heuristic labeling
- One shared execution path for the CLI and the local web app

## Architecture

Collection domains:

- `system`: hostname, operating system, uptime, CPU estimate, memory facts
- `storage`: filesystem usage relevant to endpoint capacity
- `network`: interface inventory, local addressing, interface MTU facts, supplemental ARP or neighbor evidence
- `routing`: default route and route summary
- `dns`: resolver inventory and hostname resolution checks
- `connectivity`: generic TCP reachability plus optional ping and traceroute
- `vpn`: heuristic tunnel and VPN signals
- `services`: intended endpoint reachability for configured targets

Model boundaries:

- Collectors gather raw evidence and warnings only.
- `models.py` defines the normalized structures used by the rest of the system.
- `findings.py` evaluates rules against normalized facts.
- `runner.py` builds the full result object used everywhere else.
- `serializers.py`, `report.py`, and the web templates render that result for different consumers.

Data flow:

```text
CLI / Web App
  -> Runner
  -> Collectors
  -> Normalized Models
  -> Findings Engine
  -> JSON / Terminal Report / HTML
```

This boundary keeps platform parsing out of the reporting layers and keeps interface logic out of the execution flow.

## Usage

Run the default diagnostics flow:

```bash
occams-beard run
```

Run selected domains only:

```bash
occams-beard run --checks host,network,routing,dns,connectivity
```

Override service and connectivity targets:

```bash
occams-beard run --target github.com:443 --target 1.1.1.1:53
```

In the web app, the form maps to the same runner inputs: selected domains, TCP targets, DNS hosts, and optional ping or traceroute.

## Tradeoffs and limitations

- Incomplete data is preserved as warnings and partial state rather than forced into stronger conclusions.
- No baseline check requires elevated privileges, so some platforms may expose less detail.
- Route normalization is conservative and can mark route state as `suspect` when the source data is incomplete or inconsistent.
- Supplemental ARP and neighbor evidence is contextual only and never required for a successful run.
- Optional traceroute and VPN signals can support a finding without being treated as authoritative proof.

## Future work

- Expand captured fixtures for platform-specific parser coverage
- Improve handling for more complex routing and tunnel topologies
- Add optional raw command capture for offline review when it can remain local and explicit
