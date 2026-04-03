"""Collection-plan summaries for the local web experience."""

from __future__ import annotations

from occams_beard.execution import DOMAIN_LABELS

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
        "probe_summary": probe_summary(
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


def probe_summary(
    *,
    enable_ping: bool,
    enable_trace: bool,
    capture_raw_commands: bool,
) -> str:
    """Summarize which deeper probes were enabled for the run."""

    labels: list[str] = []
    if enable_ping:
        labels.append("Ping")
    if enable_trace:
        labels.append("Traceroute")
    if capture_raw_commands:
        labels.append("Raw command capture")
    return ", ".join(labels) if labels else "Standard plan only"
