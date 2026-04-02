"""Deterministic findings engine for endpoint diagnostics."""

from __future__ import annotations

from endpoint_diagnostics_lab.models import (
    CollectedFacts,
    Finding,
    ResourceState,
    ServiceCheck,
    TcpConnectivityCheck,
    VpnSignal,
)
from endpoint_diagnostics_lab.utils.validation import is_private_or_loopback_host


SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "info": 0}


def evaluate_findings(facts: CollectedFacts) -> tuple[list[Finding], str]:
    """Evaluate deterministic findings and derive a probable fault domain."""

    findings: list[Finding] = []
    findings.extend(_evaluate_network_path(facts))
    findings.extend(_evaluate_dns_path(facts))
    findings.extend(_evaluate_resource_pressure(facts.resources))
    findings.extend(_evaluate_trace_results(facts))
    findings.extend(_evaluate_vpn_path(facts))

    if not findings:
        findings.append(
            Finding(
                identifier="healthy-baseline",
                severity="info",
                title="No major diagnostic findings detected",
                summary="The collected facts did not match any major fault rule.",
                evidence=[
                    "Deterministic rule evaluation completed without triggering fault signatures."
                ],
                probable_cause="No major failure domain was identified from the collected evidence.",
                fault_domain="healthy",
                confidence=0.8,
            )
        )

    findings.sort(key=lambda item: (SEVERITY_RANK[item.severity], item.confidence), reverse=True)
    probable_fault_domain = findings[0].fault_domain if findings else "unknown"
    return findings, probable_fault_domain


def evaluate_selected_findings(
    facts: CollectedFacts,
    selected_checks: list[str],
) -> tuple[list[Finding], str]:
    """Evaluate only the rules supported by the completed diagnostic domains."""

    enabled = set(selected_checks)
    findings: list[Finding] = []

    if {"routing", "connectivity"} <= enabled:
        findings.extend(_evaluate_network_path(facts))
    if {"dns", "connectivity"} <= enabled:
        findings.extend(_evaluate_dns_path(facts))
    if {"resources", "storage"} & enabled:
        findings.extend(_evaluate_resource_pressure(facts.resources))
    if "connectivity" in enabled:
        findings.extend(_evaluate_trace_results(facts))
    if {"vpn", "services"} <= enabled:
        findings.extend(_evaluate_vpn_path(facts))

    if not findings:
        findings.append(
            Finding(
                identifier="healthy-baseline",
                severity="info",
                title="No major diagnostic findings detected",
                summary="The collected facts did not match any enabled fault rule.",
                evidence=[
                    "Deterministic rule evaluation completed without triggering enabled fault signatures."
                ],
                probable_cause="No major failure domain was identified from the collected evidence.",
                fault_domain="healthy",
                confidence=0.8,
            )
        )

    findings.sort(key=lambda item: (SEVERITY_RANK[item.severity], item.confidence), reverse=True)
    probable_fault_domain = findings[0].fault_domain if findings else "unknown"
    return findings, probable_fault_domain


def _evaluate_network_path(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    route_summary = facts.network.route_summary

    if not route_summary.has_default_route and not facts.connectivity.internet_reachable:
        findings.append(
            Finding(
                identifier="no-default-route-no-internet",
                severity="high",
                title="No default route and no external reachability",
                summary="The endpoint lacks a default route and could not establish external TCP connectivity.",
                evidence=[
                    "Routing summary shows no default route.",
                    "All configured external TCP connectivity checks failed.",
                ],
                probable_cause="The most likely failure domain is the local network configuration on the host or access segment.",
                fault_domain="local_network",
                confidence=0.95,
            )
        )

    tcp_checks = facts.connectivity.tcp_checks
    successful_dns = [check for check in facts.dns.checks if check.success]
    multiple_tcp_failures = len([check for check in tcp_checks if not check.success]) >= 2
    any_tcp_success = any(check.success for check in tcp_checks)

    if successful_dns and multiple_tcp_failures and not any_tcp_success:
        findings.append(
            Finding(
                identifier="dns-success-tcp-failure",
                severity="medium",
                title="Name resolution works but external TCP connectivity fails",
                summary="DNS lookups succeeded, but external TCP reachability failed across multiple targets.",
                evidence=[
                    "At least one DNS hostname resolved successfully.",
                    "Multiple external TCP checks failed.",
                ],
                probable_cause="Firewall, proxy interception, or upstream egress filtering is more likely than a DNS outage.",
                fault_domain="internet_edge",
                confidence=0.8,
            )
        )

    return findings


def _evaluate_dns_path(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    dns_checks = facts.dns.checks
    if not dns_checks:
        return findings

    all_dns_failed = all(not check.success for check in dns_checks)
    raw_ip_success = any(
        check.success and is_private_or_loopback_host(check.target.host) is False and _target_is_numeric_ip(check)
        for check in facts.connectivity.tcp_checks
    )

    if all_dns_failed and raw_ip_success:
        findings.append(
            Finding(
                identifier="dns-failure-raw-ip-success",
                severity="high",
                title="DNS resolution failed but raw IP connectivity succeeded",
                summary="The endpoint can reach an external IP directly, but hostname resolution failed.",
                evidence=[
                    "All configured DNS hostnames failed to resolve.",
                    "At least one TCP connectivity check to a numeric IP address succeeded.",
                ],
                probable_cause="The most likely failure domain is the local or upstream DNS resolver path.",
                fault_domain="dns",
                confidence=0.92,
            )
        )

    return findings


def _evaluate_resource_pressure(resources: ResourceState) -> list[Finding]:
    findings: list[Finding] = []
    memory = resources.memory
    disks = resources.disks

    if memory.total_bytes and memory.available_bytes is not None:
        available_ratio = memory.available_bytes / memory.total_bytes
        cpu_hot = (
            resources.cpu.utilization_percent_estimate is not None
            and resources.cpu.utilization_percent_estimate >= 90
        )
        if available_ratio <= 0.10:
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
                        [f"CPU utilization estimate is {resources.cpu.utilization_percent_estimate:.1f}%."]
                        if cpu_hot
                        else []
                    ),
                    probable_cause="Local host resource contention is likely affecting application or interactive performance.",
                    fault_domain="local_host",
                    confidence=0.82 if cpu_hot else 0.72,
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
                    probable_cause="Local storage exhaustion is likely to impact host stability, logging, or application writes.",
                    fault_domain="local_host",
                    confidence=0.9,
                )
            )

    return findings


def _evaluate_trace_results(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    for trace in facts.connectivity.trace_results:
        if trace.partial and any(hop.address for hop in trace.hops):
            findings.append(
                Finding(
                    identifier=f"partial-trace-{trace.target}",
                    severity="low",
                    title=f"Partial traceroute observed for {trace.target}",
                    summary="Traceroute returned early hops but did not fully complete.",
                    evidence=[
                        f"Traceroute produced {len(trace.hops)} hop records.",
                        "At least one hop returned successfully before later loss or filtering.",
                    ],
                    probable_cause="Upstream filtering, path control, or ICMP suppression may exist beyond the local network.",
                    fault_domain="upstream_network",
                    confidence=0.6,
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
        findings.append(
            Finding(
                identifier="vpn-signal-private-resource-failure",
                severity="medium",
                title="VPN or tunnel appears active while private targets remain unreachable",
                summary="A VPN-like interface is present, but private resource checks still failed.",
                evidence=_vpn_evidence(facts.vpn.signals, private_service_failures),
                probable_cause="The tunnel may be established, but its routes, security policy, or remote network path may be incomplete.",
                fault_domain="vpn",
                confidence=0.74,
                heuristic=True,
            )
        )
    return findings


def _vpn_evidence(signals: list[VpnSignal], failures: list[ServiceCheck]) -> list[str]:
    evidence = [
        f"VPN heuristic matched interface {signal.interface_name} ({signal.signal_type}, confidence {signal.confidence:.2f})."
        for signal in signals
    ]
    evidence.extend(
        f"Private target {check.target.host}:{check.target.port} failed with {check.error or 'an unknown error'}."
        for check in failures
    )
    return evidence


def _target_is_numeric_ip(check: TcpConnectivityCheck) -> bool:
    host = check.target.host
    return all(character.isdigit() or character == "." for character in host)
