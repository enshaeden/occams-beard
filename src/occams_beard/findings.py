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
) -> tuple[list[Finding], str]:
    """Evaluate only the rules supported by the completed diagnostic domains."""

    enabled = set(selected_checks)
    findings: list[Finding] = []

    if {"network", "routing", "connectivity"} & enabled:
        findings.extend(_evaluate_network_path(facts))
    if {"dns", "connectivity"} <= enabled:
        findings.extend(_evaluate_dns_path(facts))
    if {"resources", "storage"} & enabled:
        findings.extend(_evaluate_resource_pressure(facts))
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


def _evaluate_resource_pressure(facts: CollectedFacts) -> list[Finding]:
    resources = facts.resources
    findings: list[Finding] = []
    memory = resources.memory
    disks = resources.disks
    cpu_hot = (
        resources.cpu.utilization_percent_estimate is not None
        and resources.cpu.utilization_percent_estimate >= 90
    )
    low_memory = False

    if memory.total_bytes and memory.available_bytes is not None:
        available_ratio = memory.available_bytes / memory.total_bytes
        low_memory = available_ratio <= 0.10
        if low_memory:
            findings.append(
                Finding(
                    identifier="high-memory-pressure",
                    severity="medium",
                    title="High memory pressure detected",
                    summary="Available memory is critically low relative to total system memory.",
                    evidence=[
                        f"Available memory ratio is {available_ratio:.1%}.",
                        f"Memory pressure classification is {memory.pressure_level or 'unknown'}.",
                    ]
                    + (
                        [
                            (
                                "CPU utilization estimate is "
                                f"{resources.cpu.utilization_percent_estimate:.1f}%."
                            )
                        ]
                        if cpu_hot
                        else []
                    ),
                    probable_cause=(
                        "Local host resource contention is likely affecting "
                        "application or interactive performance."
                    ),
                    fault_domain="local_host",
                    confidence=0.82 if cpu_hot else 0.72,
                )
            )

    if low_memory and cpu_hot and _has_degraded_connectivity(facts):
        findings.append(
            Finding(
                identifier="host-pressure-with-connectivity-degradation",
                severity="medium",
                title="Resource pressure may be contributing to degraded connectivity",
                summary=(
                    "The endpoint is under severe CPU and memory pressure while "
                    "connectivity checks are also degraded."
                ),
                evidence=[
                    (
                        "CPU utilization estimate is "
                        f"{resources.cpu.utilization_percent_estimate:.1f}%."
                    ),
                    (
                        "Available memory is "
                        f"{_format_ratio(memory.available_bytes, memory.total_bytes)} "
                        "of total."
                    ),
                    _connectivity_pressure_evidence(facts),
                ],
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

    for disk in disks:
        free_ratio = disk.free_bytes / disk.total_bytes if disk.total_bytes else 1.0
        if free_ratio <= 0.10:
            findings.append(
                Finding(
                    identifier=f"low-disk-space-{disk.path}",
                    severity="medium",
                    title=f"Low disk free space on {disk.path}",
                    summary="A monitored filesystem is at or above the low-space threshold.",
                    evidence=[
                        f"Filesystem {disk.path} is {disk.percent_used:.1f}% utilized.",
                        f"Free space ratio is {free_ratio:.1%}.",
                    ],
                    probable_cause=(
                        "Local storage exhaustion is likely to impact host "
                        "stability, logging, or application writes."
                    ),
                    fault_domain="local_host",
                    confidence=0.9,
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
                title="Storage device health reports a failure state",
                summary=(
                    "At least one storage device reported an explicit failing or unhealthy state."
                ),
                evidence=_storage_device_evidence(failed_devices),
                probable_cause=(
                    "The local storage subsystem is reporting a device-level fault that may affect "
                    "boot, read, or write stability."
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
                title="Storage device health reports a warning state",
                summary=(
                    "At least one storage device reported a warning state even though it is not "
                    "yet marked failed."
                ),
                evidence=_storage_device_evidence(warning_devices),
                probable_cause=(
                    "The local storage subsystem is signaling degraded device health that may "
                    "become operationally significant."
                ),
                fault_domain="local_host",
                confidence=0.82,
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
