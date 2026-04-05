"""Network- and DNS-focused deterministic findings rules."""

from __future__ import annotations

from occams_beard.findings_common import (
    dedupe_preserve_order,
    format_dns_hosts,
    format_tcp_targets,
    target_is_numeric_ip,
)
from occams_beard.models import CollectedFacts, Finding
from occams_beard.utils.validation import is_private_or_loopback_host


def evaluate_network_path(facts: CollectedFacts) -> list[Finding]:
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
    non_loopback_active = non_loopback_active_interfaces(facts)
    route_inconsistency = route_inconsistency_evidence(facts)
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
                    "No non-loopback local addresses were collected from interface inventory.",
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
                    f"External TCP checks failed: {format_tcp_targets(failed_public_tcp)}.",
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
        and route_inconsistency
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
                evidence=route_inconsistency
                + [f"External TCP checks failed: {format_tcp_targets(failed_public_tcp)}."],
                probable_cause=(
                    "The route table contains a default path, but the host "
                    "still appears locally misrouted, attached to the wrong "
                    "interface, or missing a usable next-hop path."
                ),
                fault_domain="local_network",
                confidence=0.9 if len(route_inconsistency) >= 2 else 0.81,
            )
        )

    if (
        route_summary.has_default_route
        and not route_inconsistency
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
                    f"Successful DNS lookups: {format_dns_hosts(successful_dns)}.",
                    f"External TCP checks failed: {format_tcp_targets(failed_public_tcp)}.",
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
                    "Successful external TCP checks: "
                    f"{format_tcp_targets(successful_public_tcp)}.",
                    f"Failed external TCP checks: {format_tcp_targets(failed_public_tcp)}.",
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


def evaluate_dns_path(facts: CollectedFacts) -> list[Finding]:
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
        if check.success and target_is_numeric_ip(check)
    ]
    raw_ip_success = any(
        check.success
        and not is_private_or_loopback_host(check.target.host)
        and target_is_numeric_ip(check)
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
                    f"DNS hostnames that failed to resolve: {format_dns_hosts(failed_dns)}.",
                    (
                        "Numeric IP TCP success observed: "
                        f"{format_tcp_targets(successful_numeric_ip_checks)}."
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
                    f"Successful DNS lookups: {format_dns_hosts(successful_dns)}.",
                    f"Failed DNS lookups: {format_dns_hosts(failed_dns)}.",
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


def evaluate_trace_results(facts: CollectedFacts) -> list[Finding]:
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


def non_loopback_active_interfaces(facts: CollectedFacts) -> list[str]:
    names: list[str] = []
    for interface in facts.network.interfaces:
        if not interface.is_up or interface.type_hint == "loopback":
            continue
        names.append(interface.name)
    return names


def route_inconsistency_evidence(facts: CollectedFacts) -> list[str]:
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
    return dedupe_preserve_order(evidence)
