# Finding Rules

## Boundary

Findings remain deterministic and evidence-based.

- The findings engine still evaluates normalized facts after collection completes.
- It still does not invent causes from uncollected data.
- Heuristic conclusions are still labeled explicitly.
- The public findings entrypoint stays narrow, while rule evaluation is split by
  concern so time, network, storage, and host-pressure logic remain reviewable.

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
Guided summaries may suppress or downgrade findings that conflict with intake scope, but raw findings remain intact in result artifacts.

## Scope

The findings engine still reasons about:

- local host pressure
- symptom-correlated local host pressure for slow-device runs
- deterministic storage-pressure states from monitored filesystems
- explicit distinction between filesystem space exhaustion and storage-device health degradation
- deterministic local clock and timezone state
- optional bounded clock-skew comparison when the operator explicitly enables it
- local network state
- DNS failures and partial failures
- generic connectivity failures
- selected service-path failures
- heuristic VPN or tunnel issues
- explicit battery-service or storage-health states reported by the operating system

It still does not become an application-layer diagnosis engine or an auto-remediation system.
It still does not infer hardware failure from cycle counts, generic low charge, or opaque vendor tooling that is not exposed through the current non-privileged collection path.

## Local Host Pressure Notes

- CPU pressure now prefers logical-core saturation evidence over generic utilization alone.
- Memory pressure can incorporate optional swap or commit pressure when the platform exposes it.
- Slow-device findings can explicitly state when current network checks do not support a network-based explanation.
- Bounded process hints are summaries only. They are coarse categories from one snapshot, not a process inventory or a sustained trend.

## Time Notes

- Time findings stay bounded to local clock state, local timezone configuration, and an optional one-shot skew comparison against a single explicit external reference.
- The external skew comparison is trustworthy only when the HTTPS reference can be certificate-validated in the current run.
- Strong time findings require strong evidence. The tool only claims material clock inaccuracy when the bounded skew check succeeds and the measured skew is large enough to matter operationally.
- If the external reference check fails, cannot be certificate-validated, or was not enabled, the tool does not silently invent drift conclusions. It records the local time state and, when needed, states that clock drift remains inconclusive.
- Time findings can explicitly note when selected DNS or connectivity checks looked healthy, which helps distinguish clock-related secure-service failures from a generic network explanation.
- The project does not synchronize time, change timezone settings, run a background clock agent, or claim to measure sustained drift trends.

## Storage Notes

- Storage findings stay deterministic and snapshot-based. They only use current filesystem capacity plus the non-privileged storage-health signals already exposed by the platform collectors.
- Low-space findings are split between warning and critical severity so the report can distinguish operational risk from likely application-stability impact.
- Storage pressure classification is role-aware. It treats low free percentage as the main danger signal, combines it with role-specific free-byte floors, and does not let tiny helper volumes become critical solely because they have small absolute capacity.
- macOS APFS helper and ephemeral mounts remain visible in collected facts, but they are diagnostic context by default. Primary writable volumes such as `/` and `/System/Volumes/Data` are the default basis for storage-space incidents and guided cleanup/escalation advice.
- Zero-capacity pseudo-mounts remain visible in collected facts, but they are excluded from storage-pressure reasoning and labeled as non-capacity diagnostic context.
- Shared-capacity APFS mounts are deduplicated for storage-pressure findings and summaries so one underlying capacity condition does not appear as several independent incidents.
- Storage-device health findings remain bounded to explicit healthy, warning, degraded, failing, or unhealthy states surfaced by the operating system. They do not infer device failure from generic slowness alone.
- Storage findings do not inject unrelated routing, DNS, or TCP-success evidence into local disk incidents.
- Absence findings such as `no-significant-storage-pressure` stay narrow. They mean the current snapshot did not expose strong local storage pressure, not that historical or intermittent storage issues are impossible.

## VPN Notes

- VPN collection remains heuristic unless the platform exposes stronger state directly.
- macOS `utun*` interfaces are not treated as meaningful active VPN sessions by default. Tunnel presence alone is weaker than a default-route change or clear route ownership.
- The output distinguishes tunnel presence from stronger likely-active signals by using different heuristic signal types and confidences.

## Intake-Aware Guidance Notes

- Intake-aware guidance is deterministic: it uses only captured intake context (`selected_symptom`, `resolved_intent`, `scope_rationale`) and collected evidence.
- Scope-awareness only affects guided narrative prioritization. It does not mutate or remove raw findings.
- Findings outside selected symptom scope are withheld from guided summaries unless they are high-severity, non-heuristic, and strongly supported by multiple evidence points.
