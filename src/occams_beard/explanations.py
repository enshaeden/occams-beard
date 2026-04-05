"""Deterministic explanation helpers layered on top of shared findings."""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from occams_beard.models import (
    CollectedFacts,
    DiagnosticProfile,
    DomainExecution,
    Finding,
    GuidedExperience,
)
from occams_beard.storage_policy import classify_disk_pressure, is_actionable_volume_role

if TYPE_CHECKING:
    from occams_beard.intake.models import IntakeContext

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
    "system-clock-materially-inaccurate": {
        "plain_language": (
            "System clock appears inaccurate; secure sign-in or TLS validation may fail."
        ),
        "safe_next_actions": [
            (
                "Review local date, time, and timezone settings without "
                "changing them during evidence capture."
            ),
            "Capture a support bundle while the skew evidence is still current.",
        ],
        "escalation_triggers": [
            "Escalate if the endpoint clock remains materially inaccurate across repeated checks.",
        ],
        "uncertainty_notes": [
            (
                "The skew reading comes from one bounded external reference check. It is strong "
                "evidence of a local time problem, but it is still a one-time comparison."
            ),
        ],
    },
    "local-time-may-impact-secure-service-access": {
        "plain_language": (
            "Local time may be far enough off to affect sign-in, certificates, or secure services."
        ),
        "safe_next_actions": [
            "Keep the current evidence and compare with any documented local time settings.",
        ],
        "escalation_triggers": [
            "Escalate if secure service failures persist and the same skew pattern repeats.",
        ],
        "uncertainty_notes": [
            (
                "This identifies elevated clock skew, but not whether time is the only problem "
                "affecting the service path."
            ),
        ],
    },
    "timezone-configuration-inconsistent": {
        "plain_language": (
            "Timezone configuration looks inconsistent with the observed local clock offset."
        ),
        "safe_next_actions": [
            "Review the configured timezone identifier before changing any local settings.",
        ],
        "escalation_triggers": [
            (
                "Escalate if timezone inconsistency persists or coincides "
                "with auth or certificate errors."
            ),
        ],
        "uncertainty_notes": [
            (
                "This finding identifies a mismatch in timezone state, not how the inconsistency "
                "was introduced."
            ),
        ],
    },
    "insufficient-clock-drift-evidence": {
        "plain_language": (
            "This run did not capture enough external reference evidence to confirm clock drift."
        ),
        "safe_next_actions": [
            "Rerun with the bounded skew check enabled if clock drift is still suspected.",
        ],
        "escalation_triggers": [
            "Escalate if secure service failures persist but clock evidence remains inconclusive.",
        ],
        "uncertainty_notes": [
            (
                "Local time state was still collected. The missing piece is a conclusive external "
                "reference comparison."
            ),
        ],
    },
    "no-significant-time-issue": {
        "plain_language": (
            "No major time-related issue was detected from the collected evidence."
        ),
        "safe_next_actions": [
            "Keep the bounded skew check enabled in future secure-service troubleshooting runs.",
        ],
        "escalation_triggers": [
            (
                "Escalate if the symptom persists and other local or "
                "service-path evidence becomes stronger."
            ),
        ],
        "uncertainty_notes": [
            (
                "This means the local clock looked close to the bounded reference in this run; "
                "it does not prove the clock was healthy at every earlier moment."
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
            "Escalate if critical free-space pressure remains on a primary writable volume.",
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
            "Escalate if low free space persists on a primary writable volume.",
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
    facts: CollectedFacts,
    profile: DiagnosticProfile | None = None,
    intake_context: IntakeContext | None = None,
) -> GuidedExperience:
    """Create a deterministic self-service summary from findings and execution state."""

    what_we_know: list[str] = []
    likely_happened: list[str] = []
    safe_next_steps: list[str] = []
    escalation_guidance: list[str] = []
    uncertainty_notes: list[str] = []

    scope_context = _build_scope_context(intake_context)

    guidance_safe_findings = []
    for finding in findings:
        if not _finding_is_guidance_safe(finding, facts):
            continue
        scope_relevance = _finding_scope_relevance(finding, intake_context)
        if scope_relevance == "inconsistent" and not _is_critical_well_supported(finding):
            continue
        guidance_safe_findings.append(finding)

    if scope_context:
        what_we_know.append(scope_context)

    for finding in guidance_safe_findings[:3]:
        scope_relevance = _finding_scope_relevance(finding, intake_context)
        if finding.heuristic:
            prefix = "Heuristic conclusion"
        else:
            what_we_know.append(finding.plain_language or finding.summary)
            prefix = "Likely explanation"
        if scope_relevance == "adjacent":
            likely_happened.append(
                f"{prefix} (adjacent to selected scope): {finding.probable_cause}"
            )
        elif scope_relevance == "inconsistent":
            likely_happened.append(
                f"{prefix} (outside selected scope, retained due to strength): "
                f"{finding.probable_cause}"
            )
            uncertainty_notes.append(
                "A high-severity finding outside the selected symptom scope was retained "
                "because evidence strength was high."
            )
        else:
            likely_happened.append(f"{prefix}: {finding.probable_cause}")
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

    if findings and not guidance_safe_findings:
        uncertainty_notes.append(
            "Guided summary withheld unsupported or internally inconsistent findings."
        )
    elif len(guidance_safe_findings) < len(findings):
        uncertainty_notes.append(
            "Some findings were downgraded or withheld because they did not align with the "
            "selected symptom scope."
        )

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


def _finding_is_guidance_safe(finding: Finding, facts: CollectedFacts) -> bool:
    if not finding.evidence:
        return False
    if finding.identifier in {
        "critical-disk-space-exhaustion",
        "low-disk-space-operational-risk",
    }:
        return _storage_finding_is_guidance_safe(finding, facts)
    if finding.identifier == "no-significant-storage-pressure":
        return not _storage_issue_present(facts)
    if finding.identifier == "vpn-signal-private-resource-failure":
        return any(
            signal.signal_type
            in {
                "default-route-tunnel-heuristic",
                "route-owned-tunnel-heuristic",
                "interface-name-and-address-heuristic",
            }
            for signal in facts.vpn.signals
        )
    return True


def _build_scope_context(intake_context: IntakeContext | None) -> str | None:
    if intake_context is None:
        return None
    symptom = intake_context.selected_symptom_label or intake_context.selected_symptom_key
    intent = intake_context.resolved_intent_key or "unresolved-intent"
    rationale = intake_context.scope_rationale or "unspecified"
    if symptom:
        return (
            "Checks were scoped for the reported symptom "
            f"'{symptom}' (intent={intent}, scope_reason={rationale})."
        )
    return f"Checks were scoped by intake context (intent={intent}, scope_reason={rationale})."


def _finding_scope_relevance(
    finding: Finding,
    intake_context: IntakeContext | None,
) -> str:
    if intake_context is None:
        return "direct"
    intent_key = intake_context.resolved_intent_key
    if intent_key in {None, "", "general_triage", "support_bundle_preparation"}:
        return "direct"

    direct_domains = _INTENT_DIRECT_FAULT_DOMAINS.get(intent_key, set())
    adjacent_domains = _INTENT_ADJACENT_FAULT_DOMAINS.get(intent_key, set())
    if finding.fault_domain in direct_domains:
        return "direct"
    if finding.fault_domain in adjacent_domains:
        return "adjacent"
    return "inconsistent"


def _is_critical_well_supported(finding: Finding) -> bool:
    return (
        finding.severity == "high"
        and finding.confidence >= 0.85
        and len(_dedupe(finding.evidence)) >= 2
        and not finding.heuristic
    )


_INTENT_DIRECT_FAULT_DOMAINS: dict[str, set[str]] = {
    "internet_connectivity_loss": {"local_network", "dns", "internet_edge"},
    "partial_access_or_dns": {"dns", "internet_edge", "upstream_network"},
    "vpn_or_private_resource_access": {"vpn", "upstream_network", "dns"},
    "local_performance_degradation": {"local_host"},
    "clock_or_trust_failure": {"local_host", "dns"},
}

_INTENT_ADJACENT_FAULT_DOMAINS: dict[str, set[str]] = {
    "internet_connectivity_loss": {"vpn", "upstream_network", "unknown"},
    "partial_access_or_dns": {"local_network", "vpn", "unknown"},
    "vpn_or_private_resource_access": {"local_network", "internet_edge", "unknown"},
    "local_performance_degradation": {"local_network", "unknown"},
    "clock_or_trust_failure": {"internet_edge", "unknown"},
}


def _storage_finding_is_guidance_safe(finding: Finding, facts: CollectedFacts) -> bool:
    path_text = _storage_path_from_title(finding.title)
    if path_text is None:
        return False
    candidate_paths = [part.strip() for part in path_text.split(" and ")]
    disks = [disk for disk in facts.resources.disks if disk.path in candidate_paths]
    if not disks:
        return False
    if any(not is_actionable_volume_role(disk.role_hint) for disk in disks):
        return False
    expected_level = "critical" if finding.identifier == "critical-disk-space-exhaustion" else "low"
    return any(
        classify_disk_pressure(
            total_bytes=disk.total_bytes,
            free_bytes=disk.free_bytes,
            role_hint=disk.role_hint,
        )
        == expected_level
        for disk in disks
        if disk.total_bytes > 0
    )


def _storage_issue_present(facts: CollectedFacts) -> bool:
    if any(
        is_actionable_volume_role(disk.role_hint)
        and disk.total_bytes > 0
        and classify_disk_pressure(
            total_bytes=disk.total_bytes,
            free_bytes=disk.free_bytes,
            role_hint=disk.role_hint,
        )
        in {"critical", "low"}
        for disk in facts.resources.disks
    ):
        return True
    return any(
        status is not None
        and any(marker in status.lower() for marker in ("fail", "warning", "degraded"))
        for device in facts.resources.storage_devices
        for status in (device.health_status, device.operational_status)
    )


def _storage_path_from_title(title: str) -> str | None:
    for prefix in (
        "Critical disk-space exhaustion on ",
        "Low available disk space may affect local operations on ",
    ):
        if title.startswith(prefix):
            return title.removeprefix(prefix)
    return None
