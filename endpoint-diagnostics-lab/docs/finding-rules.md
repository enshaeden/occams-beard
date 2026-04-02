# Finding Rules

The findings engine is deterministic by design. It maps observed evidence to likely fault domains without inventing causes that were not supported by collected facts.

## Rule Design Principles

- evidence first
- no speculative root cause without supporting facts
- confidence should reflect certainty limits
- heuristic conclusions must be labeled explicitly
- findings should map to operator-relevant fault domains

## Current Rule Set

### No default route plus no internet reachability

Condition:
- routing checks show no default route
- external TCP connectivity checks do not succeed

Likely fault domain:
- `local_network`

Interpretation:
- the endpoint or its immediate access network is probably misconfigured or disconnected

### DNS failure plus raw IP TCP success

Condition:
- configured DNS hostnames fail to resolve
- at least one external numeric IP remains reachable over TCP

Likely fault domain:
- `dns`

Interpretation:
- routing and basic internet access exist, but hostname resolution is failing

### DNS success plus repeated external TCP failure

Condition:
- DNS succeeds for at least one hostname
- multiple external TCP targets fail
- no external TCP target succeeds

Likely fault domain:
- `internet_edge`

Interpretation:
- firewall policy, proxy enforcement, or upstream egress control is more likely than DNS failure

### High memory pressure

Condition:
- available memory falls to a low ratio relative to total memory
- confidence increases if CPU estimate is also elevated

Likely fault domain:
- `local_host`

Interpretation:
- local resource contention may be degrading applications or interactivity

### Low disk free space

Condition:
- monitored filesystem free space ratio falls to 10% or below

Likely fault domain:
- `local_host`

Interpretation:
- storage exhaustion may affect logging, package updates, caches, or application writes

### Partial traceroute with successful early hops

Condition:
- traceroute returns at least some early hops
- later hops remain incomplete

Likely fault domain:
- `upstream_network`

Interpretation:
- filtering, path control, or ICMP suppression may exist beyond the local network

This finding is heuristic because traceroute behavior depends heavily on network policy.

### VPN signal active plus private target unreachable

Condition:
- a tunnel or VPN-like interface is detected heuristically
- private address targets still fail

Likely fault domain:
- `vpn`

Interpretation:
- the tunnel may exist but may not be carrying the expected routes or remote access path

This finding is heuristic because interface-name-based VPN detection is not authoritative.

## Confidence Model

Confidence values are not statistical probabilities. They are operator guidance values reflecting how strongly the observed evidence supports the finding.

General interpretation:
- `0.90+`: strong direct evidence
- `0.70-0.89`: credible evidence with some ambiguity
- `0.50-0.69`: heuristic or incomplete evidence

## Non-Goals

The findings engine does not:
- prescribe automatic remediation
- infer business-specific policies
- claim certainty for VPN state from naming heuristics alone
- attempt application-layer diagnosis beyond the configured checks
