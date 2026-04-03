"""Mode-aware presentation helpers for the local web UI."""

from __future__ import annotations

from collections import OrderedDict
import re
from typing import TYPE_CHECKING

from occams_beard.execution import DOMAIN_LABELS
from occams_beard.models import (
    DnsResolutionCheck,
    EndpointDiagnosticResult,
    Finding,
    PingResult,
    ServiceCheck,
    TcpConnectivityCheck,
    TraceResult,
)

if TYPE_CHECKING:
    from occams_beard.runner import DiagnosticsRunOptions

SELF_SERVE_MODE = "self-serve"
SUPPORT_MODE = "support"

MODE_OPTIONS = (
    {
        "id": SELF_SERVE_MODE,
        "label": "Check My Device",
        "description": (
            "Start with safe checks and plain-language results. You do not need "
            "to know networking terms to use this path."
        ),
        "badge": "Employee-safe",
    },
    {
        "id": SUPPORT_MODE,
        "label": "Work With Support",
        "description": (
            "Use this when IT or support asked for deeper testing, a specific "
            "profile, or a support-ready bundle."
        ),
        "badge": "Technician-directed",
    },
)

SYMPTOM_OPTIONS = (
    {
        "id": "internet-not-working",
        "label": "Internet not working",
        "description": (
            "Websites and online apps are not connecting, or everything looks offline."
        ),
        "profile_id": "no-internet",
        "support_profile_id": "no-internet",
    },
    {
        "id": "apps-sites-not-loading",
        "label": "Apps or sites not loading",
        "description": (
            "Some apps, sites, or sign-in pages stall, fail, or only partly load."
        ),
        "profile_id": "dns-issue",
        "support_profile_id": "internal-service-unreachable",
    },
    {
        "id": "vpn-or-company-resource-issue",
        "label": "VPN or company resource issue",
        "description": (
            "A VPN, internal app, file share, or company-only service is not working."
        ),
        "profile_id": "vpn-issue",
        "support_profile_id": "vpn-issue",
    },
    {
        "id": "device-feels-slow",
        "label": "Device feels slow",
        "description": (
            "The device feels unusually slow, overloaded, or unstable while you work."
        ),
        "profile_id": "device-slow",
        "support_profile_id": "device-slow",
    },
    {
        "id": "something-else",
        "label": "Something else",
        "description": (
            "You need a general local check before deciding what kind of help you need."
        ),
        "profile_id": "custom-profile",
        "support_profile_id": "custom-profile",
    },
)

DOMAIN_SUMMARIES = {
    "host": "Identify the device and capture the basic local host state.",
    "resources": "Check CPU and memory pressure that can make the device unstable.",
    "storage": "Check for disk pressure that can block normal device behavior.",
    "network": "Look at local network adapters, addresses, and active links.",
    "routing": "Check whether the device has a usable path off the local network.",
    "dns": "Test whether common names can be resolved safely.",
    "connectivity": "Run safe baseline reachability checks to known targets.",
    "vpn": "Look for tunnel and VPN signals without changing local state.",
    "services": "Test the intended service path or company resource target.",
}

STATUS_LABELS = {
    "passed": "Passed",
    "failed": "Failed",
    "partial": "Partial",
    "unsupported": "Unsupported",
    "skipped": "Skipped",
    "not_run": "Not run",
}

FAULT_DOMAIN_LABELS = {
    "healthy": "No major fault identified",
    "local_host": "Local device",
    "local_network": "Local network path",
    "dns": "Name resolution",
    "internet_edge": "Internet edge or egress policy",
    "vpn": "VPN or tunnel path",
    "upstream_network": "Service or upstream network path",
    "unknown": "Still uncertain",
}


def list_mode_options() -> list[dict[str, str]]:
    """Return the two top-level experience paths."""

    return [dict(option) for option in MODE_OPTIONS]


def list_symptom_options() -> list[dict[str, str]]:
    """Return the plain-language symptom choices for self-serve mode."""

    return [dict(option) for option in SYMPTOM_OPTIONS]


def normalize_mode(raw_value: str | None) -> str | None:
    """Normalize a mode query or form value."""

    if raw_value in {None, ""}:
        return None
    if raw_value in {SELF_SERVE_MODE, SUPPORT_MODE}:
        return raw_value
    raise ValueError("Unknown experience path.")


def get_mode_option(mode: str | None) -> dict[str, str] | None:
    """Return metadata for a mode identifier."""

    if mode is None:
        return None
    for option in MODE_OPTIONS:
        if option["id"] == mode:
            return dict(option)
    raise ValueError("Unknown experience path.")


def get_symptom_option(symptom_id: str | None) -> dict[str, str] | None:
    """Return metadata for a plain-language symptom identifier."""

    if symptom_id in {None, ""}:
        return None
    for option in SYMPTOM_OPTIONS:
        if option["id"] == symptom_id:
            return dict(option)
    raise ValueError("Unknown symptom choice.")


def resolve_self_serve_profile_id(symptom_id: str | None) -> str | None:
    """Map a self-serve symptom choice to a backing local profile."""

    option = get_symptom_option(symptom_id)
    return option["profile_id"] if option else None


def build_collection_plan(
    *,
    selected_checks: list[str],
    targets: list[str],
    dns_hosts: list[str],
    enable_ping: bool,
    enable_trace: bool,
    capture_raw_commands: bool,
) -> dict[str, object]:
    """Build a concise description of the current collection plan."""

    collection_items = [
        {
            "id": check,
            "label": DOMAIN_LABELS.get(check, check.replace("-", " ").title()),
            "description": DOMAIN_SUMMARIES.get(check, "Collect local diagnostic evidence."),
        }
        for check in selected_checks
    ]
    probe_labels: list[str] = []
    if enable_ping:
        probe_labels.append("Ping")
    if enable_trace:
        probe_labels.append("Traceroute")
    if capture_raw_commands:
        probe_labels.append("Raw command capture")
    egress_domains = [
        DOMAIN_LABELS.get(check, check)
        for check in selected_checks
        if check in {"dns", "connectivity", "services"}
    ]
    has_network_activity = bool(egress_domains or enable_ping or enable_trace)

    return {
        "collection_items": collection_items,
        "selected_domain_count": len(collection_items),
        "targets_count": len(targets),
        "dns_host_count": len(dns_hosts),
        "egress_domains": egress_domains,
        "probe_labels": probe_labels,
        "probe_summary": _probe_summary(
            enable_ping=enable_ping,
            enable_trace=enable_trace,
            capture_raw_commands=capture_raw_commands,
        ),
        "has_network_activity": has_network_activity,
        "network_activity_summary": (
            "This plan may send a small amount of network traffic to confirm DNS, "
            "reachability, or service paths."
            if has_network_activity
            else "This plan stays on the device and does not create intentional network traffic."
        ),
        "capture_raw_commands": capture_raw_commands,
        "raw_capture_summary": (
            "Raw command output will be collected for an optional support bundle."
            if capture_raw_commands
            else "Raw command output stays off unless support asks for it."
        ),
    }


def suggest_support_profile_id(
    result: EndpointDiagnosticResult,
    *,
    symptom_id: str | None = None,
    current_profile_id: str | None = None,
) -> str:
    """Choose the most relevant guided-support starting profile."""

    if result.probable_fault_domain == "dns":
        return "dns-issue"
    if result.probable_fault_domain == "vpn":
        return "vpn-issue"
    if result.probable_fault_domain == "local_host":
        return "device-slow"
    if result.probable_fault_domain in {"upstream_network"}:
        return "internal-service-unreachable"
    if result.probable_fault_domain in {"local_network", "internet_edge"}:
        return "no-internet"

    symptom = get_symptom_option(symptom_id)
    if symptom is not None:
        return symptom["support_profile_id"]
    if current_profile_id:
        return current_profile_id
    return "custom-profile"


def build_results_view(
    *,
    result: EndpointDiagnosticResult,
    options: DiagnosticsRunOptions,
    mode: str,
    continue_with_support_url: str | None = None,
    previous_results_url: str | None = None,
) -> dict[str, object]:
    """Build a mode-aware view model for the results page."""

    top_finding = result.findings[0] if result.findings else None
    guided = result.guided_experience
    all_execution = list(result.execution)
    selected_execution = [record for record in result.execution if record.selected]
    optional_execution = [
        record for record in all_execution if not record.selected and record.domain != "host"
    ]
    degraded_execution = [
        record
        for record in selected_execution
        if record.status in {"failed", "partial", "unsupported", "skipped"}
    ]
    warnings = _dedupe_strings(
        [f"[{warning.domain}:{warning.code}] {warning.message}" for warning in result.warnings]
    )
    mode_option = get_mode_option(mode)
    if mode_option is None:
        raise ValueError("Unknown experience path.")

    if top_finding and top_finding.severity in {"high", "medium"}:
        rollup_tone = "attention"
        rollup_label = "Needs attention"
    elif degraded_execution or warnings:
        rollup_tone = "partial"
        rollup_label = "Partial result"
    else:
        rollup_tone = "clear"
        rollup_label = "No major issue found"

    fault_domain_label = FAULT_DOMAIN_LABELS.get(
        result.probable_fault_domain,
        result.probable_fault_domain.replace("_", " ").title(),
    )
    top_takeaway = (
        (top_finding.plain_language or top_finding.summary)
        if top_finding is not None
        else "No major diagnostic finding was confirmed in this run."
    )
    what_we_know = _section_items(
        guided.what_we_know if guided is not None else [],
        fallback=(
            [top_finding.evidence_summary or top_takeaway]
            if top_finding is not None
            else ["The current run did not match a major failure signature."]
        ),
        exclude=[top_takeaway],
    )
    likely_happened = _section_items(
        guided.likely_happened if guided is not None else [],
        fallback=(
            [top_finding.probable_cause]
            if top_finding is not None
            else ["No single root cause could be confirmed from this run."]
        ),
        exclude=[top_takeaway, *what_we_know],
    )
    next_steps = _section_items(
        guided.safe_next_steps if guided is not None else [],
        fallback=[
            (
                "Download the support bundle and continue with support."
                if mode == SUPPORT_MODE
                else "Continue with support if the issue is still happening."
            )
        ],
        exclude=[*what_we_know, *likely_happened],
    )
    escalation_guidance = _section_items(
        guided.escalation_guidance if guided is not None else [],
        fallback=["Contact support if the issue is still reproducible after the safe steps."],
        exclude=[*next_steps],
    )
    uncertainty_notes = _build_uncertainty_notes(
        mode=mode,
        tone=rollup_tone,
        top_finding=top_finding,
        degraded_execution=degraded_execution,
        warnings=warnings,
        source_notes=(guided.uncertainty_notes if guided is not None else []),
        continue_with_support=continue_with_support_url is not None,
    )
    primary_next_step = _primary_next_step(
        mode=mode,
        tone=rollup_tone,
        next_steps=next_steps,
        escalation_guidance=escalation_guidance,
        continue_with_support=continue_with_support_url is not None,
        raw_capture_available=bool(result.raw_command_capture),
    )

    technical_findings = [_finding_view(finding) for finding in result.findings]
    evidence_based_findings = [
        finding for finding in technical_findings if finding["conclusion_type"] == "Evidence-based"
    ]
    heuristic_findings = [
        finding for finding in technical_findings if finding["conclusion_type"] == "Heuristic"
    ]

    selected_domains = [_selected_domain_view(record) for record in selected_execution]

    privacy_notes = _dedupe_strings(
        [
            "Everything in this run stayed on this device unless you choose to download an export.",
            (
                "This run created network traffic for the selected DNS, reachability, or service checks."
                if any(record.creates_network_egress for record in selected_execution)
                else "This run stayed local-only and did not create intentional network traffic."
            ),
            (
                "Raw command capture is available for this run and stays excluded unless you turn it on in the support bundle."
                if result.raw_command_capture
                else "Raw command capture was not collected for this run."
            ),
        ]
    )

    technical_sections = [
        _build_check_section(
            title="Generic reachability",
            items=[
                _tcp_check_view(check) for check in result.facts.connectivity.tcp_checks
            ],
            empty_message="No generic TCP checks were collected.",
        ),
        _build_check_section(
            title="DNS resolution",
            items=[_dns_check_view(check) for check in result.facts.dns.checks],
            empty_message="No DNS lookups were collected.",
        ),
        _build_check_section(
            title="Configured services",
            items=[_service_check_view(check) for check in result.facts.services.checks],
            empty_message="No configured service checks were collected.",
        ),
        _build_check_section(
            title="Optional probes",
            items=[
                *[_ping_result_view(item) for item in result.facts.connectivity.ping_checks],
                *[_trace_result_view(item) for item in result.facts.connectivity.trace_results],
            ],
            empty_message="No optional probes were collected in this run.",
        ),
    ]

    technical_context = _dedupe_strings(
        [
            (
                f"Battery health: {_battery_context(result)}."
                if "resources" in result.metadata.selected_checks
                else "Battery health: not collected."
            ),
            (
                f"Storage device health: {_storage_device_context(result)}."
                if "storage" in result.metadata.selected_checks
                else "Storage device health: not collected."
            ),
            f"Active interfaces: {_joined_or_none(result.facts.network.active_interfaces)}.",
            f"Local addresses: {_joined_or_none(result.facts.network.local_addresses)}.",
            (
                "Default route: "
                f"{result.facts.network.route_summary.default_gateway or 'none'} "
                f"via {result.facts.network.route_summary.default_interface or 'none'}."
            ),
            (
                "Route observations: "
                f"{'; '.join(result.facts.network.route_summary.observations)}."
                if result.facts.network.route_summary.observations
                else "Route observations: none."
            ),
            (
                f"Resolvers: {', '.join(result.facts.dns.resolvers)}."
                if result.facts.dns.resolvers
                else "Resolvers: none detected."
            ),
        ]
    )
    what_was_tested_summary = [
        {
            "label": "Check areas run",
            "value": f"{len(selected_execution)} selected",
        },
        {
            "label": "Optional deeper areas",
            "value": (
                "None left out"
                if not optional_execution
                else f"{len(optional_execution)} not selected"
            ),
        },
        {
            "label": "Deeper probes",
            "value": _probe_summary(
                enable_ping=options.enable_ping,
                enable_trace=options.enable_trace,
                capture_raw_commands=options.capture_raw_commands,
            ),
        },
        {
            "label": "Raw capture",
            "value": (
                "Collected and available for bundle review"
                if result.raw_command_capture
                else "Not collected in this run"
            ),
        },
    ]
    bundle_contents = [
        "A redacted JSON copy of the local result",
        "A human-readable text report",
        "A redaction report",
        "A manifest with file hashes for the bundle files",
    ]
    if result.raw_command_capture:
        bundle_contents.append("Optional raw command output if you choose to include it")

    return {
        "mode": mode,
        "mode_label": mode_option["label"],
        "mode_badge": mode_option["badge"],
        "status_tone": rollup_tone,
        "status_label": rollup_label,
        "headline": _headline_for_result(
            mode=mode,
            tone=rollup_tone,
            top_finding=top_finding,
        ),
        "top_takeaway": top_takeaway,
        "primary_next_step": primary_next_step,
        "fault_domain_label": fault_domain_label,
        "profile_name": result.metadata.profile_name,
        "issue_category": result.metadata.issue_category,
        "answer_meta": [
            {"label": "Fault domain", "value": fault_domain_label},
            {
                "label": "Plan",
                "value": result.metadata.profile_name or "General local diagnostics run",
            },
            {"label": "Run time", "value": f"{result.metadata.elapsed_ms} ms"},
        ],
        "what_we_know": what_we_know,
        "likely_happened": likely_happened,
        "next_steps": next_steps,
        "escalation_guidance": escalation_guidance,
        "uncertainty_notes": uncertainty_notes,
        "what_was_tested_summary": what_was_tested_summary,
        "selected_domains": selected_domains,
        "optional_domains": [record.label for record in optional_execution],
        "warning_notes": warnings,
        "privacy_notes": privacy_notes,
        "bundle_intro": (
            "Use this as the main handoff to support. It contains the local result, a readable report, redaction details, and file checksums."
            if mode == SUPPORT_MODE
            else "If you still need help, use the support bundle instead of screenshots so support receives the full local result."
        ),
        "bundle_contents": bundle_contents,
        "bundle_raw_capture_label": (
            "Raw command capture available"
            if result.raw_command_capture
            else "Raw command capture not collected"
        ),
        "bundle_raw_capture_note": (
            "This run collected raw command output. It stays excluded unless you turn it on below."
            if result.raw_command_capture
            else "This run did not collect raw command output, so the bundle will include only the standard files."
        ),
        "bundle_redaction_note": "Safe redaction is selected by default for most support handoffs.",
        "support_actions_intro": (
            "Use the bundle above for the main handoff. These links are for follow-up review."
            if mode == SUPPORT_MODE
            else "If support asks for additional detail, these exports are available here."
        ),
        "technical_sections": technical_sections,
        "technical_context": technical_context,
        "evidence_based_findings": evidence_based_findings,
        "heuristic_findings": heuristic_findings,
        "technical_open": mode == SUPPORT_MODE,
        "continue_with_support_url": continue_with_support_url,
        "previous_results_url": previous_results_url,
        "selected_target_count": len(options.targets),
        "selected_dns_host_count": len(options.dns_hosts),
    }


def _headline_for_result(
    *,
    mode: str,
    tone: str,
    top_finding: Finding | None,
) -> str:
    if tone == "clear":
        return (
            "This device check did not confirm a major issue."
            if mode == SELF_SERVE_MODE
            else "This support-guided run did not confirm a major issue."
        )
    if tone == "partial":
        return (
            "We found some useful signals, but this run did not isolate a single cause."
            if mode == SELF_SERVE_MODE
            else "Your device completed most checks successfully, but one or more deeper checks stayed incomplete."
        )
    if top_finding is not None:
        return top_finding.title
    return (
        "We found something that needs attention."
        if mode == SELF_SERVE_MODE
        else "This support-guided run found something that needs attention."
    )


def _finding_view(finding: Finding) -> dict[str, object]:
    evidence = _dedupe_strings(list(finding.evidence))
    return {
        "title": finding.title,
        "severity": finding.severity,
        "severity_label": finding.severity.title(),
        "summary": finding.summary,
        "plain_language": finding.plain_language or finding.summary,
        "evidence_summary": finding.evidence_summary or (evidence[0] if evidence else None),
        "evidence": evidence[:4],
        "conclusion_type": "Heuristic" if finding.heuristic else "Evidence-based",
        "probable_cause": finding.probable_cause,
        "confidence": f"{finding.confidence:.2f}",
        "fault_domain": FAULT_DOMAIN_LABELS.get(
            finding.fault_domain,
            finding.fault_domain.replace("_", " ").title(),
        ),
    }


def _build_check_section(
    *,
    title: str,
    items: list[dict[str, object]],
    empty_message: str,
) -> dict[str, object]:
    notable_items = [item for item in items if item["status"] != "passed"]
    return {
        "title": title,
        "items": items,
        "notable_items": notable_items,
        "passed_count": len([item for item in items if item["status"] == "passed"]),
        "empty_message": empty_message,
        "has_items": bool(items),
    }


def _tcp_check_view(check: TcpConnectivityCheck) -> dict[str, object]:
    detail_parts = []
    if check.target.label:
        detail_parts.append(check.target.label)
    if check.latency_ms is not None:
        detail_parts.append(f"{check.latency_ms:.1f} ms")
    if check.ip_used:
        detail_parts.append(f"via {check.ip_used}")
    if check.error:
        detail_parts.append(check.error)
    return {
        "label": f"{check.target.host}:{check.target.port}",
        "status": "passed" if check.success else "failed",
        "status_label": "Passed" if check.success else "Failed",
        "detail": ", ".join(detail_parts) if detail_parts else "No extra details recorded.",
    }


def _dns_check_view(check: DnsResolutionCheck) -> dict[str, object]:
    if check.success:
        status = "passed"
        detail = (
            ", ".join(check.resolved_addresses[:3])
            if check.resolved_addresses
            else "Resolved."
        )
    elif check.error == "hostname-resolution-timeout":
        status = "partial"
        detail = "Lookup timed out before a resolver answer was returned."
    else:
        status = "failed"
        detail = check.error or "No extra details recorded."
    return {
        "label": check.hostname,
        "status": status,
        "status_label": STATUS_LABELS[status],
        "detail": detail,
    }


def _service_check_view(check: ServiceCheck) -> dict[str, object]:
    detail_parts = [f"{check.target.host}:{check.target.port}"]
    if check.latency_ms is not None:
        detail_parts.append(f"{check.latency_ms:.1f} ms")
    if check.error:
        detail_parts.append(check.error)
    return {
        "label": check.target.label or check.target.host,
        "status": "passed" if check.success else "failed",
        "status_label": "Passed" if check.success else "Failed",
        "detail": ", ".join(detail_parts),
    }


def _ping_result_view(ping: PingResult) -> dict[str, object]:
    detail_parts = []
    if ping.average_latency_ms is not None:
        detail_parts.append(f"{ping.average_latency_ms:.1f} ms average")
    if ping.packet_loss_percent is not None:
        detail_parts.append(f"{ping.packet_loss_percent:.1f}% loss")
    if ping.error:
        detail_parts.append(ping.error)
    return {
        "label": f"Ping {ping.target}",
        "status": "passed" if ping.success else "failed",
        "status_label": "Passed" if ping.success else "Failed",
        "detail": ", ".join(detail_parts) if detail_parts else "No extra details recorded.",
    }


def _trace_result_view(trace: TraceResult) -> dict[str, object]:
    if trace.success:
        status = "passed"
        detail = (
            f"Reached {trace.target_address or trace.target} in {len(trace.hops)} hop(s)."
        )
    elif trace.partial:
        status = "partial"
        if trace.last_responding_hop is not None:
            detail = f"Stopped after hop {trace.last_responding_hop} before reaching the target."
        else:
            detail = "The trace returned some hops but did not reach the target."
    elif not trace.ran:
        status = "unsupported"
        detail = trace.error or "The trace command was not available."
    else:
        status = "failed"
        detail = trace.error or "The trace failed."
    return {
        "label": f"Trace {trace.target}",
        "status": status,
        "status_label": STATUS_LABELS[status],
        "detail": detail,
    }


def _fallback_list(values: list[str], *, fallback: list[str]) -> list[str]:
    deduped = _dedupe_strings(values)
    return deduped[:4] if deduped else fallback


def _section_items(
    values: list[str],
    *,
    fallback: list[str],
    exclude: list[str] | None = None,
) -> list[str]:
    excluded = {_normalize_text(item) for item in (exclude or []) if item}
    deduped = []
    seen: set[str] = set()

    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in excluded or normalized in seen:
            continue
        deduped.append(value)
        seen.add(normalized)

    if deduped:
        return deduped[:4]

    fallback_items: list[str] = []
    for value in fallback:
        normalized = _normalize_text(value)
        if not normalized or normalized in excluded or normalized in seen:
            continue
        fallback_items.append(value)
        seen.add(normalized)
    return fallback_items[:4]


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _joined_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else "none detected"


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(OrderedDict.fromkeys(value for value in values if value))


def _build_uncertainty_notes(
    *,
    mode: str,
    tone: str,
    top_finding: Finding | None,
    degraded_execution: list[object],
    warnings: list[str],
    source_notes: list[str],
    continue_with_support: bool,
) -> list[str]:
    lead_notes: list[str] = []
    if tone == "partial":
        lead_notes.append(
            "We found some useful signals, but this run did not isolate a single cause."
            if mode == SELF_SERVE_MODE
            else "Your device completed most checks successfully, but one or more deeper checks stayed incomplete."
        )
    elif tone == "attention" and degraded_execution:
        lead_notes.append(
            "This run found something that needs attention, but one or more supporting checks still finished with gaps."
        )
    elif tone == "clear":
        lead_notes.append(
            "This run stayed bounded to the selected checks, so it does not prove every layer is healthy."
        )

    if warnings and tone in {"partial", "attention"}:
        lead_notes.append(
            "One or more checks reported limitations, so the remaining uncertainty is best reviewed with support."
        )
    elif top_finding is None and degraded_execution:
        lead_notes.append(
            "The collected evidence stayed incomplete enough that support review is the safest next step."
        )

    if continue_with_support and tone in {"partial", "attention"}:
        lead_notes.append("The next best step is to continue with support.")

    return _section_items(
        [*lead_notes, *source_notes],
        fallback=["This run stays bounded to the selected checks and does not prove every layer."],
    )


def _primary_next_step(
    *,
    mode: str,
    tone: str,
    next_steps: list[str],
    escalation_guidance: list[str],
    continue_with_support: bool,
    raw_capture_available: bool,
) -> str:
    if mode == SUPPORT_MODE:
        return (
            "Download the support bundle and decide whether to include the raw command capture before you send it to support."
            if raw_capture_available
            else "Download the support bundle and send it to support so they can review the full local evidence."
        )
    if tone in {"partial", "attention"} and continue_with_support:
        return "The next best step is to continue with support so they can review a deeper guided plan."
    if next_steps:
        return next_steps[0]
    if escalation_guidance:
        return escalation_guidance[0]
    if continue_with_support:
        return "Continue with support if the problem is still happening."
    return "Rerun the check if the issue is still happening."


def _selected_domain_view(record) -> dict[str, object]:
    if record.status == "passed":
        badge_label = "Completed"
        badge_tone = "clear"
        subdued = True
    elif record.status == "failed":
        badge_label = "Needs review"
        badge_tone = "attention"
        subdued = False
    elif record.status == "partial":
        badge_label = "Mixed result"
        badge_tone = "partial"
        subdued = False
    elif record.status == "unsupported":
        badge_label = "Limited"
        badge_tone = "partial"
        subdued = False
    elif record.status == "skipped":
        badge_label = "Skipped"
        badge_tone = "not_run"
        subdued = False
    else:
        badge_label = STATUS_LABELS.get(record.status, record.status.replace("_", " ").title())
        badge_tone = "not_run"
        subdued = False

    return {
        "label": record.label,
        "badge_label": badge_label,
        "badge_tone": badge_tone,
        "subdued": subdued,
        "summary": record.summary or "No execution summary recorded.",
        "duration_label": (
            f"{record.duration_ms} ms"
            if record.duration_ms is not None
            else "Duration not recorded"
        ),
        "scope_label": (
            "Creates network traffic" if record.creates_network_egress else "Local only"
        ),
    }


def _probe_summary(
    *,
    enable_ping: bool,
    enable_trace: bool,
    capture_raw_commands: bool,
) -> str:
    labels: list[str] = []
    if enable_ping:
        labels.append("Ping")
    if enable_trace:
        labels.append("Traceroute")
    if capture_raw_commands:
        labels.append("Raw command capture")
    return ", ".join(labels) if labels else "Standard plan only"


def _battery_context(result: EndpointDiagnosticResult) -> str:
    battery = result.facts.resources.battery
    if battery is None:
        return "unavailable"
    if not battery.present:
        return "not present"

    parts = []
    if battery.charge_percent is not None:
        parts.append(f"{battery.charge_percent}%")
    if battery.status:
        parts.append(battery.status)
    if battery.condition:
        parts.append(f"condition {battery.condition}")
    if battery.health_percent is not None:
        parts.append(f"health {battery.health_percent:.1f}%")
    return ", ".join(parts) if parts else "present"


def _storage_device_context(result: EndpointDiagnosticResult) -> str:
    devices = result.facts.resources.storage_devices
    if not devices:
        return "none exposed"
    return ", ".join(
        f"{device.device_id}={device.health_status or device.operational_status or 'unknown'}"
        for device in devices[:3]
    )
