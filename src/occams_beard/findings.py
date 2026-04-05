"""Deterministic findings engine for host and network diagnostics."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from occams_beard.models import (
    CollectedFacts,
    Finding,
    ServiceCheck,
    StorageDeviceHealth,
    TcpConnectivityCheck,
    VpnSignal,
)
from occams_beard.utils.validation import is_private_or_loopback_host

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "info": 0}


def evaluate_findings(facts: CollectedFacts) -> tuple[list[Finding], str]:
    """Evaluate deterministic findings and derive a probable fault domain."""

    findings = _evaluate_all_findings(facts)
    return _finalize_findings(
        findings, baseline_summary="The collected facts did not match any major fault rule."
    )


def evaluate_selected_findings(
    facts: CollectedFacts,
    selected_checks: list[str],
    *,
    issue_category: str | None = None,
) -> tuple[list[Finding], str]:
    """Evaluate only the rules supported by the completed diagnostic domains."""

    enabled = set(selected_checks)
    findings: list[Finding] = []

    if {"network", "routing", "connectivity"} & enabled:
        findings.extend(_evaluate_network_path(facts))
    if {"dns", "connectivity"} <= enabled:
        findings.extend(_evaluate_dns_path(facts))
    if {"resources", "storage"} & enabled:
        findings.extend(
            _evaluate_resource_pressure(
                facts,
                enabled_checks=enabled,
                issue_category=issue_category,
            )
        )
        findings.extend(_evaluate_hardware_health(facts))
    if "connectivity" in enabled:
        findings.extend(_evaluate_trace_results(facts))
    if "services" in enabled:
        findings.extend(_evaluate_service_path(facts))
    if {"vpn", "services"} <= enabled:
        findings.extend(_evaluate_vpn_path(facts))

    return _finalize_findings(
        findings, baseline_summary="The collected facts did not match any enabled fault rule."
    )


def _evaluate_all_findings(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_evaluate_network_path(facts))
    findings.extend(_evaluate_dns_path(facts))
    findings.extend(_evaluate_resource_pressure(facts))
    findings.extend(_evaluate_hardware_health(facts))
    findings.extend(_evaluate_trace_results(facts))
    findings.extend(_evaluate_service_path(facts))
    findings.extend(_evaluate_vpn_path(facts))
    return findings


def _finalize_findings(
    findings: list[Finding],
    baseline_summary: str,
) -> tuple[list[Finding], str]:
    if not findings:
        findings.append(
            Finding(
                identifier="healthy-baseline",
                severity="info",
                title="No major diagnostic findings detected",
                summary=baseline_summary,
                evidence=[
                    (
                        "Deterministic rule evaluation completed without "
                        "triggering supported fault signatures."
                    )
                ],
                probable_cause=(
                    "No major failure domain was identified from the collected evidence."
                ),
                fault_domain="healthy",
                confidence=0.8,
            )
        )

    findings.sort(
        key=lambda item: (SEVERITY_RANK[item.severity], item.confidence),
        reverse=True,
    )
    probable_fault_domain = findings[0].fault_domain if findings else "unknown"
    return findings, probable_fault_domain


def _evaluate_network_path(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    route_summary = facts.network.route_summary
    public_tcp_checks = [
        check
        for check in facts.connectivity.tcp_checks
        if not is_private_or_loopback_host(check.target.host)
    ]
    failed_public_tcp = [check for check in public_tcp_checks if not check.success]
    successful_public_tcp = [check for check in public_tcp_checks if check.success]
    successful_dns = [check for check in facts.dns.checks if check.success]
    non_loopback_active = _non_loopback_active_interfaces(facts)
    route_inconsistency_evidence = _route_inconsistency_evidence(facts)
    default_route_target = (
        route_summary.default_gateway or route_summary.default_interface or "a configured interface"
    )

    if non_loopback_active and not facts.network.local_addresses:
        confidence = 0.9 if not route_summary.has_default_route else 0.78
        findings.append(
            Finding(
                identifier="active-interface-no-local-address",
                severity="high" if not route_summary.has_default_route else "medium",
                title="Active network interface lacks a usable local address",
                summary=(
                    "The endpoint reports an active non-loopback interface, "
                    "but no non-loopback local address was collected."
                ),
                evidence=[
                    f"Active non-loopback interfaces: {', '.join(non_loopback_active)}.",
                    ("No non-loopback local addresses were collected from interface inventory."),
                ]
                + (
                    ["Routing summary also shows no default route."]
                    if not route_summary.has_default_route
                    else []
                ),
                probable_cause=(
                    "Local interface configuration, DHCP assignment, or "
                    "link-state negotiation is more likely than an upstream "
                    "internet outage."
                ),
                fault_domain="local_network",
                confidence=confidence,
            )
        )

    if (
        not route_summary.has_default_route
        and not facts.connectivity.internet_reachable
        and failed_public_tcp
    ):
        findings.append(
            Finding(
                identifier="no-default-route-no-internet",
                severity="high",
                title="No default route and no external reachability",
                summary=(
                    "The endpoint lacks a default route and could not "
                    "establish external TCP connectivity."
                ),
                evidence=[
                    "Routing summary shows no default route.",
                    f"External TCP checks failed: {_format_tcp_targets(failed_public_tcp)}.",
                ]
                + (
                    [
                        (
                            "Active non-loopback interfaces are present: "
                            f"{', '.join(non_loopback_active)}."
                        )
                    ]
                    if non_loopback_active
                    else []
                ),
                probable_cause=(
                    "The most likely failure domain is the local network "
                    "configuration on the host or access segment."
                ),
                fault_domain="local_network",
                confidence=0.95,
            )
        )

    if (
        route_summary.has_default_route
        and route_inconsistency_evidence
        and failed_public_tcp
        and not successful_public_tcp
    ):
        findings.append(
            Finding(
                identifier="default-route-present-but-inconsistent",
                severity="high" if not facts.connectivity.internet_reachable else "medium",
                title="Default route exists but looks inconsistent with local interface state",
                summary=(
                    "A default route was collected, but route and interface "
                    "evidence suggest it may not be usable."
                ),
                evidence=route_inconsistency_evidence
                + [f"External TCP checks failed: {_format_tcp_targets(failed_public_tcp)}."],
                probable_cause=(
                    "The route table contains a default path, but the host "
                    "still appears locally misrouted, attached to the wrong "
                    "interface, or missing a usable next-hop path."
                ),
                fault_domain="local_network",
                confidence=0.9 if len(route_inconsistency_evidence) >= 2 else 0.81,
            )
        )

    if (
        route_summary.has_default_route
        and not route_inconsistency_evidence
        and successful_dns
        and len(failed_public_tcp) >= 2
        and not successful_public_tcp
    ):
        findings.append(
            Finding(
                identifier="route-and-dns-ok-external-tcp-failure",
                severity="medium",
                title="Routing and DNS work, but external TCP connectivity fails",
                summary=(
                    "The endpoint has a default route and successful DNS "
                    "resolution, yet multiple external TCP path checks failed."
                ),
                evidence=[
                    f"Default route is present via {default_route_target}.",
                    f"Successful DNS lookups: {_format_dns_hosts(successful_dns)}.",
                    f"External TCP checks failed: {_format_tcp_targets(failed_public_tcp)}.",
                ],
                probable_cause=(
                    "Firewall policy, egress filtering, captive interception, "
                    "or proxy enforcement is more likely than a DNS outage."
                ),
                fault_domain="internet_edge",
                confidence=0.86,
            )
        )

    if successful_public_tcp and failed_public_tcp:
        findings.append(
            Finding(
                identifier="mixed-external-tcp-results",
                severity="low",
                title="External reachability is inconsistent across targets",
                summary=(
                    "Some external path checks succeeded while others failed, "
                    "which suggests selective filtering or target-specific "
                    "reachability differences."
                ),
                evidence=[
                    (
                        "Successful external TCP checks: "
                        f"{_format_tcp_targets(successful_public_tcp)}."
                    ),
                    f"Failed external TCP checks: {_format_tcp_targets(failed_public_tcp)}.",
                ],
                probable_cause=(
                    "The endpoint can reach the internet generally, but policy "
                    "control, path asymmetry, or target-side availability may "
                    "be affecting only part of the traffic."
                ),
                fault_domain="internet_edge",
                confidence=0.64,
                heuristic=True,
            )
        )

    return findings


def _evaluate_dns_path(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    dns_checks = facts.dns.checks
    if not dns_checks:
        return findings

    successful_dns = [check for check in dns_checks if check.success]
    failed_dns = [
        check
        for check in dns_checks
        if not check.success and check.error != "hostname-resolution-timeout"
    ]
    successful_numeric_ip_checks = [
        check
        for check in facts.connectivity.tcp_checks
        if check.success and _target_is_numeric_ip(check)
    ]
    raw_ip_success = any(
        check.success
        and not is_private_or_loopback_host(check.target.host)
        and _target_is_numeric_ip(check)
        for check in facts.connectivity.tcp_checks
    )

    if failed_dns and len(failed_dns) == len(dns_checks) and raw_ip_success:
        findings.append(
            Finding(
                identifier="dns-failure-raw-ip-success",
                severity="high",
                title="DNS resolution failed but raw IP connectivity succeeded",
                summary=(
                    "The endpoint can reach an external IP directly, but "
                    "hostname resolution failed."
                ),
                evidence=[
                    f"DNS hostnames that failed to resolve: {_format_dns_hosts(failed_dns)}.",
                    (
                        "Numeric IP TCP success observed: "
                        f"{_format_tcp_targets(successful_numeric_ip_checks)}."
                    ),
                ],
                probable_cause=(
                    "The most likely failure domain is the local or upstream DNS resolver path."
                ),
                fault_domain="dns",
                confidence=0.92,
            )
        )

    if successful_dns and failed_dns:
        findings.append(
            Finding(
                identifier="dns-partial-resolution",
                severity="low",
                title="DNS resolution is only partially successful",
                summary=(
                    "Some configured hostnames resolved while others failed, "
                    "which suggests selective DNS reachability or split-horizon "
                    "behavior rather than a total DNS outage."
                ),
                evidence=[
                    f"Successful DNS lookups: {_format_dns_hosts(successful_dns)}.",
                    f"Failed DNS lookups: {_format_dns_hosts(failed_dns)}.",
                ],
                probable_cause=(
                    "Resolver selection, split-horizon DNS, or intermittent "
                    "upstream resolver reachability may be affecting only part "
                    "of the configured namespace set."
                ),
                fault_domain="dns",
                confidence=0.58,
                heuristic=True,
            )
        )

    return findings


def _evaluate_resource_pressure(
    facts: CollectedFacts,
    *,
    enabled_checks: set[str] | None = None,
    issue_category: str | None = None,
) -> list[Finding]:
    resources = facts.resources
    findings: list[Finding] = []
    memory = resources.memory
    enabled_checks = enabled_checks or set()
    cpu_pressure = _cpu_pressure_state(resources.cpu)
    memory_pressure = _memory_pressure_state(memory)
    process_snapshot = resources.process_snapshot
    local_pressure_present = cpu_pressure["present"] or memory_pressure["present"]
    combined_pressure = cpu_pressure["present"] and memory_pressure["present"]
    strong_local_pressure = bool(cpu_pressure["strong"] or memory_pressure["strong"])
    weakens_network_explanation = _network_explanation_not_supported(
        facts,
        enabled_checks=enabled_checks,
    )
    storage_pressure_findings = _storage_space_findings(
        facts,
        enabled_checks=enabled_checks,
    )
    findings.extend(storage_pressure_findings)

    if strong_local_pressure and issue_category == "device slow":
        findings.append(
            Finding(
                identifier="device-slow-local-host-pressure",
                severity="high"
                if cpu_pressure["strong"] and memory_pressure["strong"]
                else "medium",
                title="Local resource pressure is likely contributing to the device feeling slow",
                summary=(
                    "The current host snapshot shows resource pressure that lines up with the "
                    "reported slowness."
                ),
                evidence=_host_pressure_evidence(
                    facts,
                    include_network_context=weakens_network_explanation,
                ),
                probable_cause=(
                    "The endpoint appears overloaded in the current snapshot, so local host "
                    "pressure is a more credible explanation for the reported slowness than a "
                    "generic network-only problem."
                ),
                fault_domain="local_host",
                confidence=0.93 if combined_pressure else 0.87,
            )
        )

    if memory_pressure["strong"]:
        findings.append(
            Finding(
                identifier="high-memory-pressure",
                severity="high" if memory_pressure["severity"] == "high" else "medium",
                title="Severe local memory pressure is likely affecting responsiveness",
                summary=(
                    "Available memory is low enough that the operating system may be spending "
                    "time reclaiming memory or leaning on swap."
                ),
                evidence=_memory_pressure_evidence(memory, process_snapshot),
                probable_cause=(
                    "Local memory pressure is likely contributing to sluggish applications, "
                    "slow task switching, or delayed input response."
                ),
                fault_domain="local_host",
                confidence=0.9 if memory.commit_pressure_level == "high" else 0.84,
            )
        )

    if cpu_pressure["strong"]:
        findings.append(
            Finding(
                identifier="sustained-cpu-saturation",
                severity="high" if combined_pressure else "medium",
                title="Sustained CPU saturation is likely affecting responsiveness",
                summary=(
                    "Runnable CPU work is staying at or above the available logical-core "
                    "capacity in the current snapshot."
                ),
                evidence=_cpu_pressure_evidence(resources.cpu, process_snapshot),
                probable_cause=(
                    "The host currently has more CPU demand than available execution capacity, "
                    "which is likely to slow interactive work."
                ),
                fault_domain="local_host",
                confidence=0.9 if combined_pressure else 0.83,
            )
        )

    if (
        local_pressure_present
        and not strong_local_pressure
        and (
            combined_pressure
            or _snapshot_shows_multiple_pressure_vectors(process_snapshot)
        )
    ):
        findings.append(
            Finding(
                identifier="local-resource-pressure-no-dominant-source",
                severity="medium",
                title=(
                    "Local resource pressure is present, but no single dominant source stands "
                    "out"
                ),
                summary=(
                    "The device shows moderate host-pressure signals, but this snapshot does not "
                    "cleanly isolate one bottleneck."
                ),
                evidence=_host_pressure_evidence(
                    facts,
                    include_network_context=weakens_network_explanation,
                ),
                probable_cause=(
                    "The endpoint may be overloaded right now, but the current one-shot snapshot "
                    "is not strong enough to attribute the pressure to CPU alone or memory alone."
                ),
                fault_domain="local_host",
                confidence=0.7,
            )
        )

    if strong_local_pressure and _has_degraded_connectivity(facts):
        findings.append(
            Finding(
                identifier="host-pressure-with-connectivity-degradation",
                severity="medium",
                title="Resource pressure may be contributing to degraded connectivity",
                summary=(
                    "The endpoint is under local resource pressure while connectivity checks are "
                    "also degraded."
                ),
                evidence=_host_pressure_evidence(facts)
                + [_connectivity_pressure_evidence(facts)],
                probable_cause=(
                    "Host saturation may be contributing to socket timeouts, "
                    "slow name resolution, or delayed operator workflows, "
                    "though upstream issues may still exist."
                ),
                fault_domain="local_host",
                confidence=0.67,
                heuristic=True,
            )
        )

    if issue_category == "device slow" and not local_pressure_present:
        findings.append(
            Finding(
                identifier="no-significant-host-pressure",
                severity="info",
                title="No significant host-pressure signal was detected",
                summary=(
                    "This run did not capture strong CPU, memory, swap, or bounded process-load "
                    "evidence that would explain the device feeling slow."
                ),
                evidence=_no_host_pressure_evidence(resources),
                probable_cause=(
                    "The current snapshot does not support a local resource-pressure explanation "
                    "on its own."
                ),
                fault_domain="healthy",
                confidence=0.76,
            )
        )

    if issue_category == "device slow" and weakens_network_explanation:
        findings.append(
            Finding(
                identifier="network-explanation-not-supported",
                severity="info",
                title="Selected network checks do not currently explain the reported slowness",
                summary=(
                    "The network checks collected in this run do not show a matching network "
                    "failure signature."
                ),
                evidence=_network_health_evidence(facts, enabled_checks=enabled_checks),
                probable_cause=(
                    "Current evidence does not support a network-based explanation for the "
                    "reported slowness."
                ),
                fault_domain="healthy",
                confidence=0.8,
            )
        )

    if (
        issue_category == "low disk space"
        and not _storage_issue_present(resources)
    ):
        findings.append(
            Finding(
                identifier="no-significant-storage-pressure",
                severity="info",
                title=(
                    "Current storage evidence does not support a strong local "
                    "storage explanation"
                ),
                summary=(
                    "This run did not capture critically low free space or a device-health state "
                    "that would strongly explain the reported issue."
                ),
                evidence=_no_storage_pressure_evidence(resources)
                + (
                    _network_health_evidence(facts, enabled_checks=enabled_checks)
                    if _network_explanation_not_supported(
                        facts,
                        enabled_checks=enabled_checks,
                    )
                    else []
                ),
                probable_cause=(
                    "The current snapshot does not support local storage exhaustion or exposed "
                    "storage-device degradation as the dominant explanation."
                ),
                fault_domain="healthy",
                confidence=0.78,
            )
        )

    return findings


def _evaluate_hardware_health(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    battery = facts.resources.battery
    if (
        battery is not None
        and battery.present
        and _battery_condition_is_degraded(battery.condition)
    ):
        findings.append(
            Finding(
                identifier="battery-health-degraded",
                severity="medium",
                title="Battery health needs attention",
                summary=(
                    "The operating system reported a degraded battery condition on this endpoint."
                ),
                evidence=[
                    f"Battery condition is reported as {battery.condition}.",
                    (
                        "Battery health is reported as "
                        f"{battery.health_percent:.1f}% of design capacity."
                        if battery.health_percent is not None
                        else "Battery design-capacity percentage was not reported."
                    ),
                ]
                + (
                    [f"Battery cycle count is {battery.cycle_count}."]
                    if battery.cycle_count is not None
                    else []
                ),
                probable_cause=(
                    "The local battery is reporting a service or degradation state, "
                    "which can contribute to unstable local device behavior."
                ),
                fault_domain="local_host",
                confidence=0.87,
            )
        )

    failed_devices = [
        device
        for device in facts.resources.storage_devices
        if _storage_device_status(device) == "failure"
    ]
    warning_devices = [
        device
        for device in facts.resources.storage_devices
        if _storage_device_status(device) == "warning"
    ]

    if failed_devices:
        findings.append(
            Finding(
                identifier="storage-device-health-failure",
                severity="high",
                title="Storage-device health reports a failing state",
                summary=(
                    "At least one storage device reported an explicit failing or unhealthy state."
                ),
                evidence=_storage_device_evidence(failed_devices),
                probable_cause=(
                    "The local storage subsystem is reporting a device-level fault that may "
                    "affect local reads, writes, boot behavior, or application stability."
                ),
                fault_domain="local_host",
                confidence=0.93,
            )
        )
    elif warning_devices:
        findings.append(
            Finding(
                identifier="storage-device-health-warning",
                severity="medium",
                title="Storage-device health reports a degraded state",
                summary=(
                    "At least one storage device reported a warning state even though it is not "
                    "yet marked failed."
                ),
                evidence=_storage_device_evidence(warning_devices),
                probable_cause=(
                    "The local storage subsystem is signaling degraded device health that may "
                    "become operationally significant even without a total device failure."
                ),
                fault_domain="local_host",
                confidence=0.82,
            )
        )

    return findings


def _storage_space_findings(
    facts: CollectedFacts,
    *,
    enabled_checks: set[str],
) -> list[Finding]:
    findings: list[Finding] = []
    weakens_network_explanation = _network_explanation_not_supported(
        facts,
        enabled_checks=enabled_checks,
    )
    for disk in facts.resources.disks:
        pressure_level = _disk_pressure_level(disk)
        if pressure_level not in {"critical", "low"}:
            continue

        operational_impact = _storage_operational_impact(disk)
        evidence = _disk_pressure_evidence(disk)
        if operational_impact is not None:
            evidence.append(operational_impact)
        if weakens_network_explanation:
            evidence.extend(_network_health_evidence(facts, enabled_checks=enabled_checks))

        if pressure_level == "critical":
            findings.append(
                Finding(
                    identifier="critical-disk-space-exhaustion",
                    severity="high",
                    title=f"Critical disk-space exhaustion on {disk.path}",
                    summary=(
                        "Available disk space is critically low and may affect application "
                        "stability."
                    ),
                    evidence=evidence,
                    probable_cause=(
                        "Local filesystem space exhaustion is likely to affect writes, temp "
                        "files, logging, updates, or sign-in caches on this device."
                    ),
                    fault_domain="local_host",
                    confidence=0.95 if _is_operational_volume(disk) else 0.88,
                    plain_language=(
                        "Available disk space is critically low and may affect application "
                        "stability."
                    ),
                    safe_next_actions=[
                        (
                            "Remove or archive only known non-essential local files if that is "
                            "already part of the documented operator process."
                        ),
                        (
                            "Capture a support bundle before cleanup if the "
                            "storage pressure is current."
                        ),
                    ],
                    escalation_triggers=[
                        (
                            "Escalate if critical free-space pressure remains "
                            "on an operational volume."
                        ),
                    ],
                    uncertainty_notes=[
                        (
                            "This is a current capacity snapshot only; it does not prove how long "
                            "the filesystem has been this full."
                        )
                    ],
                )
            )
        else:
            findings.append(
                Finding(
                    identifier="low-disk-space-operational-risk",
                    severity="medium",
                    title=f"Low available disk space may affect local operations on {disk.path}",
                    summary=(
                        "Available disk space is low enough that local writes, logs, or updates "
                        "may start failing."
                    ),
                    evidence=evidence,
                    probable_cause=(
                        "Local storage pressure may be contributing to application failures, "
                        "unstable updates, delayed writes, or missing local logs."
                    ),
                    fault_domain="local_host",
                    confidence=0.9 if _is_operational_volume(disk) else 0.8,
                    plain_language=(
                        "Low available disk space may impact local writes, logs, or updates."
                    ),
                    safe_next_actions=[
                        (
                            "Review obvious non-essential local files first before deleting any "
                            "managed or application data."
                        ),
                        "Capture a support bundle while the low-space condition is still present.",
                    ],
                    escalation_triggers=[
                        "Escalate if low free space persists on a system or user-data volume.",
                    ],
                    uncertainty_notes=[
                        (
                            "This finding identifies storage pressure, not which application will "
                            "fail first or which file set caused the pressure."
                        )
                    ],
                )
            )
    return findings


def _evaluate_trace_results(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    for trace in facts.connectivity.trace_results:
        if trace.partial and trace.last_responding_hop is not None:
            findings.append(
                Finding(
                    identifier=f"partial-trace-{trace.target}",
                    severity="low",
                    title=f"Partial traceroute observed for {trace.target}",
                    summary="Traceroute returned early hops but did not fully complete.",
                    evidence=[
                        (
                            f"Traceroute produced {len(trace.hops)} hop records "
                            f"and last received a response at hop "
                            f"{trace.last_responding_hop}."
                        ),
                        (
                            "The trace did not reach the resolved target "
                            f"address {trace.target_address}."
                            if trace.target_address
                            else "The trace did not reach the requested target."
                        ),
                        (
                            "At least one earlier hop returned successfully "
                            "before later loss or filtering."
                        ),
                    ],
                    probable_cause=(
                        "Upstream filtering, path control, or ICMP suppression "
                        "may exist beyond the local network."
                    ),
                    fault_domain="upstream_network",
                    confidence=0.6,
                    heuristic=True,
                )
            )
    return findings


def _battery_condition_is_degraded(condition: str | None) -> bool:
    if condition is None:
        return False
    normalized = condition.strip().lower()
    degraded_markers = (
        "replace",
        "service",
        "poor",
        "check battery",
        "failure",
        "failing",
        "degraded",
        "dead",
        "overheat",
    )
    return any(marker in normalized for marker in degraded_markers)


def _storage_device_status(device: StorageDeviceHealth) -> str | None:
    raw_statuses = [
        status.strip().lower()
        for status in (device.health_status, device.operational_status)
        if status
    ]
    failure_markers = ("fail", "failing", "failed", "unhealthy", "critical")
    warning_markers = ("warning", "degraded", "predictive failure")
    healthy_markers = ("healthy", "verified", "ok")
    if any(any(marker in status for marker in failure_markers) for status in raw_statuses):
        return "failure"
    if any(any(marker in status for marker in warning_markers) for status in raw_statuses):
        return "warning"
    if raw_statuses and all(
        any(marker in status for marker in healthy_markers) for status in raw_statuses
    ):
        return "healthy"
    return None


def _storage_issue_present(resources) -> bool:
    if any(_disk_pressure_level(disk) in {"critical", "low"} for disk in resources.disks):
        return True
    return any(
        _storage_device_status(device) in {"failure", "warning"}
        for device in resources.storage_devices
    )


def _disk_pressure_level(disk) -> str:
    if disk.pressure_level in {"critical", "low", "normal"}:
        return str(disk.pressure_level)
    if disk.total_bytes <= 0:
        return "unknown"
    free_ratio = disk.free_bytes / disk.total_bytes
    if free_ratio <= 0.05 or disk.free_bytes <= 2 * 1024**3:
        return "critical"
    if free_ratio <= 0.10 or disk.free_bytes <= 10 * 1024**3:
        return "low"
    return "normal"


def _disk_pressure_evidence(disk) -> list[str]:
    free_percent = (
        f"{disk.free_percent:.1f}%"
        if disk.free_percent is not None
        else _format_ratio(disk.free_bytes, disk.total_bytes)
    )
    return [
        f"Filesystem {disk.path} is {disk.percent_used:.1f}% utilized.",
        f"Free space is {_format_bytes(disk.free_bytes)} ({free_percent} free).",
        f"Storage pressure classification for this volume is {_disk_pressure_level(disk)}.",
    ]


def _storage_operational_impact(disk) -> str | None:
    role_hint = disk.role_hint or "other"
    if role_hint == "system":
        return (
            "This appears to be a system-facing volume, so low space can affect temp files, "
            "logs, updates, caches, or sign-in state."
        )
    if role_hint == "user_data":
        return (
            "This appears to be a user-data volume, so low space can affect profile data, "
            "downloads, caches, and application writes."
        )
    return (
        "Low space on this monitored volume may still affect local writes for applications that "
        "store data there."
    )


def _is_operational_volume(disk) -> bool:
    return disk.role_hint in {"system", "user_data"}


def _storage_device_evidence(devices: list[StorageDeviceHealth]) -> list[str]:
    evidence: list[str] = []
    for device in devices:
        labels = [device.device_id]
        if device.model:
            labels.append(device.model)
        status_bits = [
            value
            for value in (
                device.health_status,
                device.operational_status,
                device.protocol,
                device.medium,
            )
            if value
        ]
        evidence.append(
            "Storage device "
            f"{' / '.join(labels)} reports "
            f"{'; '.join(status_bits) or 'an explicit health issue'}."
        )
    return evidence


def _no_storage_pressure_evidence(resources) -> list[str]:
    if not resources.disks and not resources.storage_devices:
        return ["No disk-capacity or storage-device health facts were collected in this run."]

    evidence: list[str] = []
    if resources.disks:
        healthiest = [
            (
                f"{disk.path} ({disk.free_percent:.1f}% free, "
                f"{_disk_pressure_level(disk)} pressure)"
            )
            for disk in resources.disks[:3]
            if disk.free_percent is not None
        ]
        if healthiest:
            evidence.append(f"Monitored volumes: {', '.join(healthiest)}.")
    healthy_devices = [
        device
        for device in resources.storage_devices
        if _storage_device_status(device) == "healthy"
    ]
    if healthy_devices:
        evidence.append(
            "Storage-device health reported healthy state for "
            + ", ".join(device.device_id for device in healthy_devices[:3])
            + "."
        )
    elif not resources.storage_devices:
        evidence.append("Storage-device health was not exposed on this endpoint.")
    return evidence or ["No strong local storage-risk signal was detected."]


def _evaluate_service_path(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    public_service_checks = [
        check
        for check in facts.services.checks
        if not is_private_or_loopback_host(check.target.host)
    ]
    failed_public_services = [check for check in public_service_checks if not check.success]
    successful_public_services = [check for check in public_service_checks if check.success]
    successful_service_targets = _format_service_targets(successful_public_services)
    failed_service_targets = _format_service_targets(failed_public_services)

    if (
        facts.connectivity.internet_reachable
        and failed_public_services
        and not successful_public_services
    ):
        findings.append(
            Finding(
                identifier="internet-ok-selected-service-failure",
                severity="medium",
                title="Generic internet reachability works but selected service checks fail",
                summary=(
                    "Baseline external path checks succeeded, but every "
                    "configured public service check failed."
                ),
                evidence=[
                    "Generic internet reachability checks succeeded.",
                    (
                        "Failed configured public services: "
                        f"{_format_service_targets(failed_public_services)}."
                    ),
                ],
                probable_cause=(
                    "The failure is more likely isolated to the intended "
                    "service path, intermediate policy control, or the target "
                    "service itself than to general internet access."
                ),
                fault_domain="upstream_network",
                confidence=0.79,
            )
        )

    if successful_public_services and failed_public_services:
        findings.append(
            Finding(
                identifier="mixed-service-results",
                severity="low",
                title="Configured service reachability is inconsistent",
                summary=(
                    "Some intended service checks succeeded while others "
                    "failed, which suggests target-specific policy or "
                    "availability differences."
                ),
                evidence=[
                    f"Successful configured services: {successful_service_targets}.",
                    f"Failed configured services: {failed_service_targets}.",
                ],
                probable_cause=(
                    "The endpoint retains some application reachability, but "
                    "selective filtering, service-side health, or "
                    "environment-specific policy may be affecting individual "
                    "targets."
                ),
                fault_domain="upstream_network",
                confidence=0.61,
                heuristic=True,
            )
        )

    return findings


def _evaluate_vpn_path(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    if not facts.vpn.signals:
        return findings

    private_service_failures = [
        check
        for check in facts.services.checks
        if not check.success and is_private_or_loopback_host(check.target.host)
    ]
    if private_service_failures:
        route_summary = facts.network.route_summary
        confidence = max(signal.confidence for signal in facts.vpn.signals)
        if route_summary.default_interface and any(
            signal.interface_name == route_summary.default_interface for signal in facts.vpn.signals
        ):
            confidence = max(confidence, 0.82)

        findings.append(
            Finding(
                identifier="vpn-signal-private-resource-failure",
                severity="medium",
                title=("VPN or tunnel appears active while private targets remain unreachable"),
                summary=(
                    "A VPN-like interface is present, but private resource checks still failed."
                ),
                evidence=_vpn_evidence(
                    facts.vpn.signals, private_service_failures, route_summary.default_interface
                ),
                probable_cause=(
                    "The tunnel may be established, but its routes, security "
                    "policy, or remote network path may be incomplete."
                ),
                fault_domain="vpn",
                confidence=round(confidence, 2),
                heuristic=True,
            )
        )
    return findings


def _vpn_evidence(
    signals: list[VpnSignal],
    failures: list[ServiceCheck],
    default_interface: str | None,
) -> list[str]:
    evidence = [
        (
            f"VPN heuristic matched interface {signal.interface_name} "
            f"({signal.signal_type}, confidence {signal.confidence:.2f}, "
            f"{signal.address_count} usable address{'es' if signal.address_count != 1 else ''})."
        )
        for signal in signals
    ]
    if default_interface:
        evidence.append(f"Default route uses interface {default_interface}.")
    evidence.extend(
        (
            f"Private target {check.target.host}:{check.target.port} failed "
            f"with {check.error or 'an unknown error'}."
        )
        for check in failures
    )
    return evidence


def _target_is_numeric_ip(check: TcpConnectivityCheck) -> bool:
    try:
        ipaddress.ip_address(check.target.host)
    except ValueError:
        return False
    return True


def _non_loopback_active_interfaces(facts: CollectedFacts) -> list[str]:
    names: list[str] = []
    for interface in facts.network.interfaces:
        if not interface.is_up or interface.type_hint == "loopback":
            continue
        names.append(interface.name)
    return names


def _has_degraded_connectivity(facts: CollectedFacts) -> bool:
    failed_public_tcp = [
        check
        for check in facts.connectivity.tcp_checks
        if not check.success and not is_private_or_loopback_host(check.target.host)
    ]
    return not facts.connectivity.internet_reachable or len(failed_public_tcp) >= 2


def _connectivity_pressure_evidence(facts: CollectedFacts) -> str:
    failed_public_tcp = [
        check
        for check in facts.connectivity.tcp_checks
        if not check.success and not is_private_or_loopback_host(check.target.host)
    ]
    if failed_public_tcp:
        return f"External TCP failures were observed: {_format_tcp_targets(failed_public_tcp)}."
    return "Internet reachability checks did not succeed."


def _cpu_pressure_state(cpu) -> dict[str, bool | str]:
    logical_cpus = cpu.logical_cpus or 0
    ratio_5m = (
        (cpu.load_average_5m / logical_cpus)
        if cpu.load_average_5m is not None and logical_cpus > 0
        else None
    )
    strong = bool(
        cpu.load_ratio_1m is not None
        and cpu.load_ratio_1m >= 1.25
        and ratio_5m is not None
        and ratio_5m >= 1.0
    )
    present = strong or cpu.saturation_level == "elevated"
    return {
        "present": present,
        "strong": strong,
        "ratio_5m_known": ratio_5m is not None,
    }


def _memory_pressure_state(memory) -> dict[str, bool | str]:
    available_percent = memory.available_percent or 0.0
    swap_pressure = _has_swap_pressure(memory)
    commit_pressure = memory.commit_pressure_level in {"high", "elevated"}
    strong = bool(
        memory.pressure_level == "high"
        and (
            available_percent <= 8.0
            or swap_pressure
            or memory.commit_pressure_level == "high"
        )
    )
    present = strong or memory.pressure_level == "elevated" or commit_pressure or swap_pressure
    severity = (
        "high"
        if available_percent <= 5.0 or memory.commit_pressure_level == "high"
        else "medium"
    )
    return {
        "present": present,
        "strong": strong,
        "severity": severity,
    }


def _has_swap_pressure(memory) -> bool:
    if memory.swap_used_bytes is None:
        return False
    if memory.swap_total_bytes:
        return (
            memory.swap_total_bytes > 0
            and (memory.swap_used_bytes / memory.swap_total_bytes) >= 0.25
        )
    return memory.swap_used_bytes >= 512 * 1024**2


def _snapshot_shows_multiple_pressure_vectors(snapshot) -> bool:
    if snapshot is None:
        return False
    vectors = 0
    if snapshot.high_cpu_process_count >= 2:
        vectors += 1
    if snapshot.high_memory_process_count >= 2:
        vectors += 1
    if len(snapshot.top_categories) >= 2:
        vectors += 1
    return vectors >= 2


def _host_pressure_evidence(
    facts: CollectedFacts,
    *,
    include_network_context: bool = False,
) -> list[str]:
    evidence: list[str] = []
    evidence.extend(
        _cpu_pressure_evidence(
            facts.resources.cpu,
            facts.resources.process_snapshot,
        )
    )
    evidence.extend(
        _memory_pressure_evidence(
            facts.resources.memory,
            facts.resources.process_snapshot,
        )
    )
    snapshot = facts.resources.process_snapshot
    if snapshot is not None and snapshot.sampled_process_count:
        evidence.append(
            "Bounded process snapshot sampled "
            f"{snapshot.sampled_process_count} processes and retained "
            f"{len(snapshot.top_categories)} notable category summaries."
        )
    if include_network_context:
        evidence.extend(
            _network_health_evidence(
                facts,
                enabled_checks={"routing", "dns", "connectivity"},
            )
        )
    return _dedupe_preserve_order(evidence)


def _cpu_pressure_evidence(cpu, snapshot) -> list[str]:
    evidence: list[str] = []
    if cpu.logical_cpus is not None:
        evidence.append(f"Logical CPU count is {cpu.logical_cpus}.")
    if cpu.load_average_1m is not None:
        evidence.append(
            "1-minute load average is "
            f"{cpu.load_average_1m:.2f}"
            + (
                f" ({cpu.load_ratio_1m:.2f}x logical-core capacity)."
                if cpu.load_ratio_1m is not None
                else "."
            )
        )
    if cpu.load_average_5m is not None:
        evidence.append(f"5-minute load average is {cpu.load_average_5m:.2f}.")
    if cpu.saturation_level is not None:
        evidence.append(f"CPU saturation classification is {cpu.saturation_level}.")
    if snapshot is not None and snapshot.high_cpu_process_count:
        evidence.append(
            "Bounded process snapshot found "
            f"{snapshot.high_cpu_process_count} unusually active processes."
        )
    for category in (snapshot.top_categories[:2] if snapshot is not None else []):
        if category.combined_cpu_percent_estimate is None:
            continue
        evidence.append(
            f"Process category {_format_process_category(category.category)} accounts for about "
            f"{category.combined_cpu_percent_estimate:.1f}% sampled CPU."
        )
    return evidence


def _memory_pressure_evidence(memory, snapshot) -> list[str]:
    evidence: list[str] = []
    if memory.available_percent is not None:
        evidence.append(f"Available memory is {memory.available_percent:.1f}% of total RAM.")
    if memory.pressure_level is not None:
        evidence.append(f"Memory pressure classification is {memory.pressure_level}.")
    if memory.swap_used_bytes is not None or memory.swap_total_bytes is not None:
        evidence.append(
            "Swap usage is "
            f"{_format_bytes(memory.swap_used_bytes)} / {_format_bytes(memory.swap_total_bytes)}."
        )
    if memory.committed_bytes is not None and memory.commit_limit_bytes is not None:
        evidence.append(
            "Committed memory is "
            f"{_format_bytes(memory.committed_bytes)} / {_format_bytes(memory.commit_limit_bytes)}."
        )
    if memory.commit_pressure_level is not None:
        evidence.append(f"Commit pressure classification is {memory.commit_pressure_level}.")
    if snapshot is not None and snapshot.high_memory_process_count:
        evidence.append(
            "Bounded process snapshot found "
            f"{snapshot.high_memory_process_count} unusually large resident-memory consumers."
        )
    for category in (snapshot.top_categories[:2] if snapshot is not None else []):
        if category.combined_memory_bytes is None:
            continue
        evidence.append(
            f"Process category {_format_process_category(category.category)} holds about "
            f"{_format_bytes(category.combined_memory_bytes)} of sampled resident memory."
        )
    return evidence


def _no_host_pressure_evidence(resources) -> list[str]:
    evidence = []
    evidence.append(
        f"CPU saturation classification is {resources.cpu.saturation_level or 'unknown'}."
    )
    evidence.append(
        f"Memory pressure classification is {resources.memory.pressure_level or 'unknown'}."
    )
    if resources.memory.commit_pressure_level is not None:
        evidence.append(
            f"Commit pressure classification is {resources.memory.commit_pressure_level}."
        )
    snapshot = resources.process_snapshot
    if snapshot is None:
        evidence.append("Bounded process-load hints were unavailable in this snapshot.")
    else:
        evidence.append(
            f"Bounded process snapshot found {snapshot.high_cpu_process_count} high-CPU and "
            f"{snapshot.high_memory_process_count} high-memory processes."
        )
    return evidence


def _network_explanation_not_supported(
    facts: CollectedFacts,
    *,
    enabled_checks: set[str],
) -> bool:
    if "connectivity" not in enabled_checks:
        return False

    public_tcp_checks = [
        check
        for check in facts.connectivity.tcp_checks
        if not is_private_or_loopback_host(check.target.host)
    ]
    if not public_tcp_checks or any(not check.success for check in public_tcp_checks):
        return False
    if "dns" in enabled_checks and facts.dns.checks and any(
        not check.success for check in facts.dns.checks
    ):
        return False
    if "routing" in enabled_checks and not facts.network.route_summary.has_default_route:
        return False
    return facts.connectivity.internet_reachable


def _network_health_evidence(
    facts: CollectedFacts,
    *,
    enabled_checks: set[str],
) -> list[str]:
    evidence: list[str] = []
    if "routing" in enabled_checks and facts.network.route_summary.has_default_route:
        default_route_target = (
            facts.network.route_summary.default_gateway
            or facts.network.route_summary.default_interface
            or "a configured interface"
        )
        evidence.append(
            f"Routing summary still shows a default route via {default_route_target}."
        )
    if "dns" in enabled_checks:
        successful_dns = [check for check in facts.dns.checks if check.success]
        if successful_dns:
            evidence.append(f"DNS checks succeeded: {_format_dns_hosts(successful_dns)}.")
    if "connectivity" in enabled_checks:
        public_tcp_checks = [
            check
            for check in facts.connectivity.tcp_checks
            if not is_private_or_loopback_host(check.target.host)
        ]
        successful_public_tcp = [check for check in public_tcp_checks if check.success]
        if successful_public_tcp:
            evidence.append(
                f"External TCP checks succeeded: {_format_tcp_targets(successful_public_tcp)}."
            )
        if facts.connectivity.internet_reachable:
            evidence.append("Generic internet reachability checks succeeded.")
    return evidence


def _route_inconsistency_evidence(facts: CollectedFacts) -> list[str]:
    route_summary = facts.network.route_summary
    if not route_summary.has_default_route:
        return []

    evidence = list(route_summary.observations)
    default_interface = route_summary.default_interface
    interface = next(
        (
            item
            for item in facts.network.interfaces
            if default_interface and item.name == default_interface
        ),
        None,
    )
    if default_interface is None:
        evidence.append("Route summary reported a default route but did not identify an interface.")
    elif default_interface not in facts.network.active_interfaces:
        evidence.append(
            f"Default route uses interface {default_interface}, but that "
            "interface was not collected as active."
        )

    if interface is not None:
        has_usable_non_loopback_address = any(
            not address.is_loopback for address in interface.addresses
        )
        if not has_usable_non_loopback_address:
            evidence.append(
                f"Default route uses interface {default_interface}, but that "
                "interface has no usable non-loopback address."
            )

    if route_summary.default_route_state == "suspect" and not evidence:
        evidence.append(
            "Route summary classified the default route as suspect from "
            "platform-specific route output."
        )
    return _dedupe_preserve_order(evidence)


def _format_ratio(numerator: int | None, denominator: int | None) -> str:
    if numerator is None or denominator is None or denominator == 0:
        return "an unknown ratio"
    return f"{(numerator / denominator):.1%}"


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _format_dns_hosts(checks: Iterable[object]) -> str:
    items: list[str] = []
    for check in checks:
        hostname = getattr(check, "hostname", None)
        if not isinstance(hostname, str):
            continue
        error = getattr(check, "error", None)
        if isinstance(error, str) and error:
            items.append(f"{hostname} ({error})")
            continue
        resolved_addresses = getattr(check, "resolved_addresses", None)
        if isinstance(resolved_addresses, list) and resolved_addresses:
            items.append(f"{hostname} -> {', '.join(resolved_addresses[:2])}")
            continue
        items.append(hostname)
    return ", ".join(items[:3]) + (" and more" if len(items) > 3 else "")


def _format_tcp_targets(checks: Iterable[TcpConnectivityCheck]) -> str:
    items = []
    for check in checks:
        status = "ok" if check.success else (check.error or "failed")
        items.append(f"{check.target.host}:{check.target.port} ({status})")
    return ", ".join(items[:3]) + (" and more" if len(items) > 3 else "")


def _format_service_targets(checks: Iterable[ServiceCheck]) -> str:
    items = []
    for check in checks:
        label = check.target.label or f"{check.target.host}:{check.target.port}"
        status = "ok" if check.success else (check.error or "failed")
        items.append(f"{label} ({status})")
    return ", ".join(items[:3]) + (" and more" if len(items) > 3 else "")


def _format_process_category(value: str) -> str:
    return {
        "browser": "browser",
        "collaboration": "collaboration apps",
        "container_runtime": "container runtime",
        "database": "database",
        "ide": "IDE or editor",
        "other": "other processes",
        "vm": "VM",
    }.get(value, value.replace("_", " "))


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    suffixes = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    for suffix in suffixes:
        if size < 1024 or suffix == suffixes[-1]:
            return f"{size:.1f} {suffix}"
        size /= 1024
    return f"{value} B"
