# Finding Rules

## Boundary

Findings remain deterministic and evidence-based.

- The findings engine still evaluates normalized facts after collection completes.
- It still does not invent causes from uncollected data.
- Heuristic conclusions are still labeled explicitly.

## Finding Output

Each finding now carries:

- identifier
- severity
- title
- summary
- evidence
- probable cause
- fault domain
- confidence
- heuristic flag
- plain-language explanation
- safe next actions
- escalation triggers
- uncertainty notes

The added guidance fields do not replace the deterministic finding. They are rendered from it.

## Scope

The findings engine still reasons about:

- local host pressure
- local network state
- DNS failures and partial failures
- generic connectivity failures
- selected service-path failures
- heuristic VPN or tunnel issues
- explicit battery-service or storage-health states reported by the operating system

It still does not become an application-layer diagnosis engine or an auto-remediation system.
It still does not infer hardware failure from cycle counts, generic low charge, or opaque vendor tooling that is not exposed through the current non-privileged collection path.
