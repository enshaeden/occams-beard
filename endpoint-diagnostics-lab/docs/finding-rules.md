# Finding Rules

The findings engine is deterministic by design. It maps observed evidence to likely fault domains without inventing causes that were not supported by collected facts.

## Rule Design Principles

- evidence first
- no speculative root cause without supporting facts
- confidence reflects evidence strength, not statistical probability
- heuristic conclusions are labeled explicitly
- generic connectivity and intended service reachability are reasoned about separately

## Current Rule Set

### Active interface without a usable local address

Condition:
- a non-loopback interface is up
- no non-loopback local address was collected

Likely fault domain:
- `local_network`

Interpretation:
- local interface configuration, DHCP assignment, or link-state negotiation is more likely than an upstream outage

### No default route plus no internet reachability

Condition:
- routing checks show no default route
- external TCP connectivity checks do not succeed

Likely fault domain:
- `local_network`

Interpretation:
- the endpoint or its immediate access network is probably misconfigured or disconnected

### Default route exists but local routing still looks inconsistent

Condition:
- routing checks show a default route entry
- route normalization or interface state marks that route as suspect or inconsistent
- external TCP connectivity still fails

Likely fault domain:
- `local_network`

Interpretation:
- a default path exists in the table, but the endpoint still appears locally misrouted, attached to the wrong interface, or missing a usable next hop

This rule stays conservative. It does not claim the gateway is down; it only says the host-side route evidence is not strong enough to treat the default route as healthy.

### Default route plus DNS success plus repeated external TCP failure

Condition:
- a default route is present
- the route is not already classified as suspect or locally inconsistent
- DNS succeeds for at least one hostname
- multiple external TCP targets fail
- no external public TCP target succeeds

Likely fault domain:
- `internet_edge`

Interpretation:
- broad routing exists, but egress policy, filtering, or captive interception is more likely than a DNS issue

### Mixed external TCP results

Condition:
- at least one public external TCP check succeeds
- at least one public external TCP check fails

Likely fault domain:
- `internet_edge`

Interpretation:
- selective filtering, target-specific path differences, or target-side availability may exist

This finding is heuristic because mixed results can still have multiple explanations.

### DNS failure plus raw IP TCP success

Condition:
- configured DNS hostnames fail to resolve
- at least one external numeric IP remains reachable over TCP

Likely fault domain:
- `dns`

Interpretation:
- routing and basic internet access exist, but hostname resolution is failing

### DNS partial success

Condition:
- at least one configured hostname resolves
- at least one configured hostname fails

Likely fault domain:
- `dns`

Interpretation:
- split-horizon behavior, resolver inconsistency, or intermittent resolver reachability is more likely than a total DNS outage

This finding is heuristic because the tool does not inspect resolver decision paths directly.

### High memory pressure

Condition:
- available memory falls to a low ratio relative to total memory
- confidence increases if CPU estimate is also elevated

Likely fault domain:
- `local_host`

Interpretation:
- local resource contention may be degrading applications or interactivity

### High resource pressure plus degraded connectivity

Condition:
- memory pressure is high
- CPU estimate is high
- connectivity checks are also degraded

Likely fault domain:
- `local_host`

Interpretation:
- host saturation may be contributing to degraded diagnostics or operator experience, though it does not prove the network is healthy

This finding is heuristic because host pressure and network symptoms can coexist without direct causality.

### Low disk free space

Condition:
- monitored filesystem free space ratio falls to 10% or below

Likely fault domain:
- `local_host`

Interpretation:
- storage exhaustion may affect logging, package updates, caches, or application writes

### Generic internet reachability works but selected public services fail

Condition:
- generic connectivity checks succeed
- configured public service checks fail
- no configured public service check succeeds

Likely fault domain:
- `upstream_network`

Interpretation:
- broad internet access exists, but the intended service path, intermediate policy, or the remote service may be impaired

### Mixed configured service results

Condition:
- at least one configured public service succeeds
- at least one configured public service fails

Likely fault domain:
- `upstream_network`

Interpretation:
- target-specific policy or availability differences are more likely than total endpoint isolation

This finding is heuristic because the tool does not inspect application-layer health directly.

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

Confidence values are operator guidance values describing how strongly the observed evidence supports the finding.

General interpretation:
- `0.90+`: strong direct evidence
- `0.70-0.89`: credible evidence with some ambiguity
- `0.50-0.69`: heuristic or incomplete evidence

## Non-Goals

The findings engine does not:
- prescribe automatic remediation
- infer business-specific policies
- claim certainty for VPN state from naming heuristics alone
- attempt deep application-layer diagnosis beyond the configured service checks
