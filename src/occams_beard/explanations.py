"""Deterministic explanation helpers layered on top of shared findings."""

from __future__ import annotations

from collections import OrderedDict

from occams_beard.models import (
    DiagnosticProfile,
    DomainExecution,
    Finding,
    GuidedExperience,
)

FINDING_GUIDANCE: dict[str, dict[str, object]] = {
    "healthy-baseline": {
        "plain_language": (
            "The collected evidence did not match any of the tool's major fault signatures."
        ),
        "safe_next_actions": [
            (
                "If the problem is still happening, rerun with the most relevant "
                "optional probes or a narrower profile."
            ),
        ],
        "escalation_triggers": [
            (
                "Escalate if the user-impacting issue is still reproducible but "
                "the current evidence stays inconclusive."
            ),
        ],
        "uncertainty_notes": [
            (
                "This result only says the current rules did not match a known "
                "signature; it does not prove the endpoint is healthy in every "
                "layer."
            ),
        ],
    },
    "active-interface-no-local-address": {
        "plain_language": (
            "The endpoint has an active network link but no usable non-loopback address on it."
        ),
        "safe_next_actions": [
            (
                "Reconnect the active network once so the interface can request "
                "a fresh local address."
            ),
            (
                "If Wi-Fi is in use, confirm the endpoint is joined to the "
                "intended SSID before rerunning."
            ),
        ],
        "escalation_triggers": [
            (
                "Escalate if the interface remains active but still has no "
                "usable local address after reconnecting."
            ),
        ],
        "uncertainty_notes": [
            (
                "The current evidence does not prove whether DHCP, static "
                "addressing, or link negotiation is responsible."
            ),
        ],
    },
    "no-default-route-no-internet": {
        "plain_language": (
            "The endpoint could not reach external targets and it has no usable default route."
        ),
        "safe_next_actions": [
            "Reconnect the network once and rerun to see whether a default route is restored.",
            "If a VPN is expected, reconnect it before assuming the wider network is down.",
        ],
        "escalation_triggers": [
            (
                "Escalate if no default route returns after reconnecting or "
                "renewing local network access."
            ),
        ],
        "uncertainty_notes": [
            (
                "This finding identifies the local access path as the likely "
                "failure domain, not the exact root cause."
            ),
        ],
    },
    "default-route-present-but-inconsistent": {
        "plain_language": (
            "The host has a default route on paper, but the route and interface "
            "evidence do not line up cleanly."
        ),
        "safe_next_actions": [
            "Verify the expected interface is still the active interface before rerunning.",
            "If a dock, VPN, or secondary adapter recently changed state, reconnect it once.",
        ],
        "escalation_triggers": [
            (
                "Escalate if the default route still points to an inactive or "
                "unusable interface after the interface is reset."
            ),
        ],
        "uncertainty_notes": [
            (
                "The route table inconsistency can indicate stale local state, "
                "policy routing, or an incomplete next-hop path."
            ),
        ],
    },
    "route-and-dns-ok-external-tcp-failure": {
        "plain_language": (
            "The endpoint can resolve names and has a default route, but "
            "external TCP path checks still fail."
        ),
        "safe_next_actions": [
            (
                "Verify whether the endpoint should be using a proxy, captive "
                "portal, or egress policy exception."
            ),
            "Rerun with the same profile on a known-good network if that is operationally safe.",
        ],
        "escalation_triggers": [
            "Escalate if multiple public TCP targets keep failing while DNS still succeeds.",
        ],
        "uncertainty_notes": [
            (
                "This points away from pure DNS failure, but it does not "
                "distinguish firewall policy from upstream filtering on its own."
            ),
        ],
    },
    "mixed-external-tcp-results": {
        "plain_language": "Some external targets are reachable and others are not.",
        "safe_next_actions": [
            "Keep at least one known-good public target in the run to confirm the baseline path.",
            "Compare failed targets for shared port numbers, networks, or security controls.",
        ],
        "escalation_triggers": [
            "Escalate if the same subset of public targets keeps failing across repeated runs.",
        ],
        "uncertainty_notes": [
            (
                "Selective target failures are heuristic because both local "
                "policy and remote-side conditions can look similar."
            ),
        ],
    },
    "dns-failure-raw-ip-success": {
        "plain_language": (
            "The endpoint can reach a numeric external IP, but hostname lookups are failing."
        ),
        "safe_next_actions": [
            "Compare the endpoint's resolver settings with the expected network or VPN profile.",
            "Rerun once after reconnecting the network or VPN so the resolver path is refreshed.",
        ],
        "escalation_triggers": [
            "Escalate if numeric IP access still works while hostname lookups keep failing.",
        ],
        "uncertainty_notes": [
            (
                "The finding isolates the failure toward DNS behavior, not "
                "whether the problem is local resolver selection or upstream "
                "resolver reachability."
            ),
        ],
    },
    "dns-partial-resolution": {
        "plain_language": (
            "Some hostnames resolved and others did not, so DNS behavior is "
            "inconsistent rather than completely down."
        ),
        "safe_next_actions": [
            (
                "Keep both public and environment-specific hostnames in the "
                "run so the split is visible."
            ),
            (
                "If VPN is relevant, compare results with and without the "
                "tunnel connected only if policy allows it."
            ),
        ],
        "escalation_triggers": [
            (
                "Escalate if the same namespace subset keeps failing after "
                "reconnecting the intended network path."
            ),
        ],
        "uncertainty_notes": [
            (
                "Selective DNS failures can be caused by split-horizon DNS, "
                "resolver choice, or intermittent upstream reachability."
            ),
        ],
    },
    "high-memory-pressure": {
        "plain_language": (
            "Available memory is low enough that the endpoint itself may be unstable or sluggish."
        ),
        "safe_next_actions": [
            (
                "Close non-essential heavy applications before rerunning if "
                "that is safe for the user session."
            ),
            (
                "Capture a support bundle while the pressure is still present "
                "so the evidence is current."
            ),
        ],
        "escalation_triggers": [
            "Escalate if memory pressure remains high after obvious local workload reduction.",
        ],
        "uncertainty_notes": [
            ("The tool identifies host pressure, not which application or process is responsible."),
        ],
    },
    "sustained-cpu-saturation": {
        "plain_language": (
            "CPU demand is staying high enough that the device itself is likely overloaded."
        ),
        "safe_next_actions": [
            (
                "Pause or close non-essential heavy local workloads before rerunning if that is "
                "safe for the user session."
            ),
            "Capture a support bundle while the saturation is still present.",
        ],
        "escalation_triggers": [
            "Escalate if CPU saturation remains high after obvious local workload reduction.",
        ],
        "uncertainty_notes": [
            (
                "This identifies sustained CPU pressure on the host, not which exact process is "
                "responsible."
            ),
        ],
    },
    "device-slow-local-host-pressure": {
        "plain_language": (
            "Local resource pressure is likely contributing to the device feeling slow."
        ),
        "safe_next_actions": [
            (
                "Reduce obvious local workload where that is safe, then rerun while the slow "
                "symptom is still present."
            ),
            "Capture a support bundle promptly so the snapshot remains current.",
        ],
        "escalation_triggers": [
            "Escalate if the device still feels slow and the same host-pressure pattern repeats.",
        ],
        "uncertainty_notes": [
            (
                "This is still a one-time snapshot; it does not prove how long the host pressure "
                "has been present."
            ),
        ],
    },
    "local-resource-pressure-no-dominant-source": {
        "plain_language": (
            "The device may be overloaded right now, but this snapshot does not isolate a single "
            "main bottleneck."
        ),
        "safe_next_actions": [
            "Rerun while the slow period is active so the next snapshot can confirm the pattern.",
        ],
        "escalation_triggers": [
            "Escalate if repeated runs keep showing moderate host pressure without a clear owner.",
        ],
        "uncertainty_notes": [
            (
                "This finding confirms local pressure signals exist, but not whether CPU, memory, "
                "or workload mix is the dominant driver."
            ),
        ],
    },
    "host-pressure-with-connectivity-degradation": {
        "plain_language": (
            "The endpoint is heavily loaded and that load may be contributing "
            "to the network symptoms."
        ),
        "safe_next_actions": [
            (
                "Reduce obvious local load where that is operationally safe, "
                "then rerun to see whether network symptoms change."
            ),
        ],
        "escalation_triggers": [
            (
                "Escalate if host pressure and connectivity degradation persist "
                "together across repeated runs."
            ),
        ],
        "uncertainty_notes": [
            (
                "This is a heuristic link between host load and network "
                "behavior, not proof that the host caused the path failure."
            ),
        ],
    },
    "no-significant-host-pressure": {
        "plain_language": (
            "This run did not capture a strong local CPU or memory pressure signal."
        ),
        "safe_next_actions": [
            "Rerun while the slow behavior is actively happening so the snapshot reflects it.",
        ],
        "escalation_triggers": [
            "Escalate if the device is still slow but repeated runs stay inconclusive.",
        ],
        "uncertainty_notes": [
            (
                "The tool captures a current snapshot only; it can miss short spikes or earlier "
                "pressure that already cleared."
            ),
        ],
    },
    "network-explanation-not-supported": {
        "plain_language": (
            "The selected network checks do not currently support a network-based explanation for "
            "the reported slowness."
        ),
        "safe_next_actions": [
            "Keep at least one public DNS and TCP baseline in future slow-device runs.",
        ],
        "escalation_triggers": [
            (
                "Escalate if the device stays slow but both host-pressure and network evidence "
                "remain weak."
            ),
        ],
        "uncertainty_notes": [
            (
                "This only means the selected network checks looked healthy in this run; it does "
                "not prove the network was healthy at every earlier moment."
            ),
        ],
    },
    "battery-health-degraded": {
        "plain_language": (
            "The operating system says the battery itself is degraded or needs service."
        ),
        "safe_next_actions": [
            "Keep the device on stable external power during support work if that is available.",
            "Capture a support bundle while the battery warning is still present.",
        ],
        "escalation_triggers": [
            "Escalate if the battery keeps reporting a service or replace state.",
        ],
        "uncertainty_notes": [
            (
                "This identifies a local battery health problem, not whether the battery is the "
                "only cause of the user-visible symptom."
            ),
        ],
    },
    "storage-device-health-failure": {
        "plain_language": (
            "The operating system reports that a storage device is failing or unhealthy."
        ),
        "safe_next_actions": [
            "Minimize non-essential writes until the device can be reviewed.",
            "Capture a support bundle promptly so the reported health state is preserved.",
        ],
        "escalation_triggers": [
            "Escalate immediately if the failing storage device backs the active system volume.",
        ],
        "uncertainty_notes": [
            (
                "This identifies a reported device-health fault, not the exact physical cause of "
                "the storage problem."
            ),
        ],
    },
    "storage-device-health-warning": {
        "plain_language": (
            "The operating system reports a storage-health warning even though the device is not "
            "yet marked failed."
        ),
        "safe_next_actions": [
            "Capture a support bundle before the health state changes.",
            "Avoid unnecessary heavy local write activity until the warning is reviewed.",
        ],
        "escalation_triggers": [
            "Escalate if the same storage warning persists across repeated runs.",
        ],
        "uncertainty_notes": [
            (
                "This shows an explicit health warning from the endpoint, but not whether the "
                "device will fail imminently."
            ),
        ],
    },
    "critical-disk-space-exhaustion": {
        "plain_language": (
            "Available disk space is critically low and may affect application stability."
        ),
        "safe_next_actions": [
            (
                "Free only known non-essential local space first, following the documented "
                "operator process."
            ),
            "Capture a support bundle before cleanup if the condition is still present.",
        ],
        "escalation_triggers": [
            "Escalate if critical free-space pressure remains on a monitored operational volume.",
        ],
        "uncertainty_notes": [
            (
                "This is a current capacity snapshot; it does not prove how long the filesystem "
                "has been near exhaustion."
            ),
        ],
    },
    "low-disk-space-operational-risk": {
        "plain_language": (
            "Low available disk space may impact local writes, logs, or updates."
        ),
        "safe_next_actions": [
            "Review obvious non-essential local files before deleting managed or application data.",
            "Capture a support bundle while the low-space state is still present.",
        ],
        "escalation_triggers": [
            "Escalate if low free space persists on a monitored operational volume.",
        ],
        "uncertainty_notes": [
            (
                "This finding identifies storage pressure, not which specific application will "
                "fail first."
            ),
        ],
    },
    "no-significant-storage-pressure": {
        "plain_language": (
            "Current storage evidence does not support a strong local storage explanation."
        ),
        "safe_next_actions": [
            "Rerun while the issue is active if storage pressure is still suspected.",
        ],
        "escalation_triggers": [
            (
                "Escalate if the issue persists but storage evidence remains weak across "
                "repeated runs."
            ),
        ],
        "uncertainty_notes": [
            (
                "This only reflects the current snapshot and the storage-health data the platform "
                "exposed."
            ),
        ],
    },
    "internet-ok-selected-service-failure": {
        "plain_language": (
            "General external connectivity works, but the intended service path does not."
        ),
        "safe_next_actions": [
            "Verify the service host and port are still correct before rerunning.",
            (
                "Keep one public baseline target in the run so general "
                "internet reachability remains visible."
            ),
        ],
        "escalation_triggers": [
            ("Escalate if the public baseline succeeds but the same intended service still fails."),
        ],
        "uncertainty_notes": [
            (
                "This finding narrows the issue away from general internet "
                "access, but not whether the fault is policy, path, or "
                "service-side health."
            ),
        ],
    },
    "mixed-service-results": {
        "plain_language": "Some intended services are reachable and others are not.",
        "safe_next_actions": [
            "Group failing services by network, port, or environment before escalating.",
        ],
        "escalation_triggers": [
            "Escalate if the same service subset keeps failing while others remain healthy.",
        ],
        "uncertainty_notes": [
            (
                "Mixed service results are heuristic because policy and "
                "remote-side issues can look similar."
            ),
        ],
    },
    "vpn-signal-private-resource-failure": {
        "plain_language": (
            "A tunnel or VPN signal is present, but private targets are still unreachable."
        ),
        "safe_next_actions": [
            ("Reconnect the VPN client once if that is already part of the documented workflow."),
            (
                "Keep one public baseline target in the run to separate "
                "tunnel issues from wider internet loss."
            ),
        ],
        "escalation_triggers": [
            (
                "Escalate if private targets still fail while VPN-like "
                "interfaces and routes remain present."
            ),
        ],
        "uncertainty_notes": [
            (
                "VPN state is heuristic in this tool; interface and route "
                "signals do not prove the remote network path is healthy."
            ),
        ],
    },
}


def enrich_findings(findings: list[Finding]) -> list[Finding]:
    """Attach deterministic plain-language guidance to finding objects."""

    for finding in findings:
        guidance = FINDING_GUIDANCE.get(finding.identifier, {})
        if finding.plain_language is None:
            finding.plain_language = str(guidance.get("plain_language", finding.summary))
        if finding.evidence_summary is None:
            finding.evidence_summary = _build_evidence_summary(finding)
        if not finding.safe_next_actions:
            finding.safe_next_actions = _guidance_list(guidance, "safe_next_actions")
        if not finding.escalation_triggers:
            finding.escalation_triggers = _guidance_list(guidance, "escalation_triggers")
        if not finding.uncertainty_notes:
            default_uncertainty = (
                ["This conclusion is heuristic and should be treated as guidance, not proof."]
                if finding.heuristic
                else ["No additional uncertainty was recorded beyond the collected evidence."]
            )
            finding.uncertainty_notes = _guidance_list(
                guidance,
                "uncertainty_notes",
                default=default_uncertainty,
            )
    return findings


def build_guided_experience(
    findings: list[Finding],
    execution: list[DomainExecution],
    profile: DiagnosticProfile | None = None,
) -> GuidedExperience:
    """Create a deterministic self-service summary from findings and execution state."""

    what_we_know: list[str] = []
    likely_happened: list[str] = []
    safe_next_steps: list[str] = []
    escalation_guidance: list[str] = []
    uncertainty_notes: list[str] = []

    for finding in findings[:3]:
        if finding.heuristic:
            likely_happened.append(f"Heuristic conclusion: {finding.probable_cause}")
        else:
            what_we_know.append(finding.plain_language or finding.summary)
            likely_happened.append(finding.probable_cause)
        safe_next_steps.extend(finding.safe_next_actions)
        escalation_guidance.extend(finding.escalation_triggers)
        uncertainty_notes.extend(finding.uncertainty_notes)

    for record in execution:
        if not record.selected:
            continue
        if record.status == "partial":
            uncertainty_notes.append(
                f"{record.label} was only partially collected or produced mixed results."
            )
        elif record.status == "unsupported":
            uncertainty_notes.append(f"{record.label} was unsupported on this endpoint.")
        elif record.status == "failed":
            uncertainty_notes.append(f"{record.label} failed during this run.")

    if profile is not None:
        safe_next_steps.extend(profile.safe_user_guidance)
        escalation_guidance.extend(profile.escalation_guidance)

    return GuidedExperience(
        issue_category=profile.issue_category if profile else None,
        profile_id=profile.profile_id if profile else None,
        profile_name=profile.name if profile else None,
        what_we_know=_dedupe(what_we_know),
        likely_happened=_dedupe(likely_happened),
        safe_next_steps=_dedupe(safe_next_steps),
        escalation_guidance=_dedupe(escalation_guidance),
        uncertainty_notes=_dedupe(uncertainty_notes),
    )


def _build_evidence_summary(finding: Finding) -> str:
    evidence = _dedupe(finding.evidence)
    if not evidence:
        return "No supporting evidence summary was recorded."
    if len(evidence) == 1:
        return evidence[0]
    return f"{evidence[0]} {evidence[1]}"


def _guidance_list(
    guidance: dict[str, object],
    key: str,
    *,
    default: list[str] | None = None,
) -> list[str]:
    value = guidance.get(key, default if default is not None else [])
    if not isinstance(value, list):
        return list(default or [])
    return [item for item in value if isinstance(item, str)]


def _dedupe(values: list[str]) -> list[str]:
    return list(OrderedDict.fromkeys(value for value in values if value))
