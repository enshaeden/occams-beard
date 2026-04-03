# Finding Rules

## What this is

This document defines how Occam's Beard turns collected evidence into deterministic findings.

## Problem space

Diagnostic tools lose credibility when they present likely causes without showing the evidence or when they treat missing data as if it were collected and negative. Findings need to be conservative, reviewable, and explicit about uncertainty.

## Design approach

The findings engine is evidence-first. It evaluates normalized facts after collection completes and only applies rules supported by the selected diagnostic domains. Confidence is an operator guidance value based on evidence strength, not a statistical claim. Heuristic findings are labeled as such.

Connectivity findings and service findings are separate:

- connectivity findings reason about generic path health
- service findings reason about intended endpoint reachability

That separation prevents a target-specific service failure from being described as a general internet failure.

## Key capabilities

- Deterministic rule evaluation over normalized facts
- Explicit evidence attached to every finding
- Fault-domain classification across `local_host`, `local_network`, `dns`, `internet_edge`, `upstream_network`, and `vpn`
- Heuristic labeling where the evidence is suggestive rather than direct

## Architecture

The rules are grouped by failure domain:

- local host state such as memory pressure or disk exhaustion
- local network state such as missing addressing or suspect routing
- DNS-specific failure and partial-failure conditions
- broader connectivity degradation at the internet edge
- intended service failures that occur despite baseline reachability
- VPN-related issues inferred from tunnel evidence plus private-target failures

Current rule families include:

- active interface without a usable local address
- no default route plus no internet reachability
- suspect default route with repeated external TCP failure
- default route and DNS success with repeated external TCP failure
- mixed external TCP results
- DNS failure with numeric IP TCP success
- DNS partial success
- high memory pressure
- high CPU and memory pressure with degraded connectivity
- low disk free space
- generic internet reachability with public service failure
- mixed configured service results
- partial traceroute with successful early hops
- VPN signal plus private target failure

## Usage

Read findings as operator guidance tied to observed evidence. The report and JSON both include the same fields:

- identifier
- severity
- title
- summary
- evidence
- probable cause
- fault domain
- confidence
- heuristic flag

Example interpretation:

- If DNS hostnames fail while a numeric IP target succeeds, the likely fault domain is DNS rather than general egress.
- If generic connectivity succeeds while configured public service checks fail, the likely fault domain shifts to the intended service path or remote service rather than the local host.

## Tradeoffs and limitations

- The engine does not prescribe remediation.
- It does not infer business-specific policy or service intent beyond the configured targets.
- It does not claim certainty for VPN state from interface naming or route hints alone.
- It does not perform deep application-layer diagnosis beyond TCP reachability of configured services.
- Mixed results are often heuristic because multiple explanations can fit the same evidence.

## Future work

- Add more rule coverage for split-tunnel and policy-routing cases without weakening determinism
- Expand evidence patterns where additional fixture coverage shows stable behavior across platforms
