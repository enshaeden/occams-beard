"""Human-readable report rendering."""

from __future__ import annotations

from endpoint_diagnostics_lab.models import (
    EndpointDiagnosticResult,
    Finding,
    ServiceCheck,
    TcpConnectivityCheck,
)


def render_report(result: EndpointDiagnosticResult, json_path: str | None = None) -> str:
    """Render a concise human-readable diagnostic report."""

    host = result.facts.host
    resources = result.facts.resources
    network = result.facts.network
    top_finding = result.findings[0] if result.findings else None
    selected_checks = set(result.metadata.selected_checks)

    lines = [
        "Occam's Beard Report",
        "================================",
        "",
        "Summary",
        f"- Host: {host.hostname}",
        f"- Platform: {result.platform.system} {result.platform.release} ({result.platform.machine})",
        f"- Internet reachable: {_yes_no_or_uncollected('connectivity' in selected_checks, result.facts.connectivity.internet_reachable)}",
        f"- Default route present: {_yes_no_or_uncollected('routing' in selected_checks, network.route_summary.has_default_route)}",
        f"- Probable fault domain: {result.probable_fault_domain}",
    ]

    if top_finding:
        lines.append(f"- Fault-domain basis: {top_finding.title} ({top_finding.confidence:.2f} confidence)")

    lines.extend(
        [
            "",
            "Key Findings",
        ]
    )

    for index, finding in enumerate(result.findings[:5], start=1):
        lines.extend(_render_finding(index, finding))

    lines.extend(
        [
            "",
            "System Snapshot",
            f"- Current user: {host.current_user or 'unknown'}",
            f"- Uptime (seconds): {host.uptime_seconds if host.uptime_seconds is not None else 'unknown'}",
            f"- CPU logical cores: {resources.cpu.logical_cpus if resources.cpu.logical_cpus is not None else 'unknown'}",
            f"- CPU utilization estimate: {_format_percent(resources.cpu.utilization_percent_estimate)}",
            f"- Memory pressure: {resources.memory.pressure_level or 'unknown'}",
            f"- Memory available: {_format_bytes(resources.memory.available_bytes)} / {_format_bytes(resources.memory.total_bytes)}",
            "",
            "Network Snapshot",
            f"- Active interfaces: {_join_or_none(network.active_interfaces) if 'network' in selected_checks else 'not collected'}",
            f"- Local addresses: {_join_or_none(network.local_addresses) if 'network' in selected_checks else 'not collected'}",
            f"- Interface MTUs: {_format_interface_mtu_summary(network) if 'network' in selected_checks else 'not collected'}",
            f"- ARP neighbors: {_format_arp_summary(network) if 'network' in selected_checks else 'not collected'}",
            f"- Default gateway: {_routing_value('routing' in selected_checks, network.route_summary.default_gateway)}",
            f"- Default interface: {_routing_value('routing' in selected_checks, network.route_summary.default_interface)}",
            f"- Default route state: {_routing_value('routing' in selected_checks, network.route_summary.default_route_state)}",
            f"- Route entries collected: {len(network.route_summary.routes) if 'routing' in selected_checks else 'not collected'}",
            f"- Route observations: {_routing_observations('routing' in selected_checks, network.route_summary.observations)}",
            "",
            "Generic Reachability Checks",
        ]
    )

    if "connectivity" not in selected_checks:
        lines.append("- Generic connectivity checks were not collected.")
    elif result.facts.connectivity.tcp_checks:
        for check in result.facts.connectivity.tcp_checks:
            lines.append(f"- {_format_tcp_check(check)}")
    else:
        lines.append("- No generic TCP reachability checks were collected.")

    if "connectivity" in selected_checks and result.facts.connectivity.ping_checks:
        for ping in result.facts.connectivity.ping_checks:
            state = "ok" if ping.success else f"failed ({ping.error or 'unknown-error'})"
            latency = f", avg {_format_percentless(ping.average_latency_ms)} ms" if ping.average_latency_ms is not None else ""
            loss = (
                f", loss {_format_percent(ping.packet_loss_percent)}"
                if ping.packet_loss_percent is not None
                else ""
            )
            lines.append(f"- Ping {ping.target}: {state}{latency}{loss}")

    if "connectivity" in selected_checks and result.facts.connectivity.trace_results:
        for trace in result.facts.connectivity.trace_results:
            if trace.success:
                destination = trace.target_address or trace.target
                state = f"completed with {len(trace.hops)} hops to {destination}"
            elif trace.partial:
                stopping_point = (
                    f"last response at hop {trace.last_responding_hop}"
                    if trace.last_responding_hop is not None
                    else "no responding hops"
                )
                target = trace.target_address or trace.target
                state = f"partial, {stopping_point}, target {target} not reached"
            elif not trace.ran:
                state = f"not run ({trace.error or 'unavailable'})"
            else:
                state = f"failed ({trace.error or 'unknown-error'})"
            lines.append(f"- Trace {trace.target}: {state}")

    lines.extend(["", "DNS Resolution"])
    if "dns" not in selected_checks:
        lines.append("- DNS checks were not collected.")
    elif result.facts.dns.resolvers:
        lines.append(f"- Resolvers: {', '.join(result.facts.dns.resolvers)}")
    else:
        lines.append("- Resolvers: none detected")

    if "dns" not in selected_checks:
        pass
    elif result.facts.dns.checks:
        for check in result.facts.dns.checks:
            if check.success:
                detail = ", ".join(check.resolved_addresses[:3]) if check.resolved_addresses else "resolved"
                lines.append(f"- {check.hostname}: ok ({detail})")
            else:
                lines.append(f"- {check.hostname}: failed ({check.error or 'unknown-error'})")
    else:
        lines.append("- No DNS checks were collected.")

    lines.extend(["", "Configured Service Checks"])
    if "services" not in selected_checks:
        lines.append("- Service checks were not collected.")
    elif result.facts.services.checks:
        for check in result.facts.services.checks:
            lines.append(f"- {_format_service_check(check)}")
    else:
        lines.append("- No operator-supplied service checks were collected.")

    lines.extend(
        [
            "",
            "Probable Fault Domain",
            f"- {result.probable_fault_domain}",
        ]
    )

    if top_finding:
        lines.append(f"- Justification: {top_finding.probable_cause}")

    if json_path:
        lines.extend(["", f"Raw JSON artifact: {json_path}"])

    if result.warnings:
        lines.extend(["", "Warnings and degraded checks"])
        for warning in result.warnings:
            lines.append(f"- [{warning.domain}:{warning.code}] {warning.message}")

    return "\n".join(lines)


def _render_finding(index: int, finding: Finding) -> list[str]:
    lines = [
        f"{index}. [{finding.severity.upper()}] {finding.title}",
        f"   Derived finding: {finding.summary}",
    ]
    for evidence in finding.evidence[:3]:
        lines.append(f"   Observed fact: {evidence}")
    if len(finding.evidence) > 3:
        lines.append(f"   Observed fact: {len(finding.evidence) - 3} more supporting signal(s) not shown")
    if finding.heuristic:
        lines.append(f"   Heuristic conclusion: {finding.probable_cause}")
    else:
        lines.append(f"   Probable cause: {finding.probable_cause}")
    lines.append(
        f"   Fault domain: {finding.fault_domain} ({finding.confidence:.2f} confidence, {'heuristic' if finding.heuristic else 'evidence-based'})"
    )
    return lines


def _format_tcp_check(check: TcpConnectivityCheck) -> str:
    state = "ok" if check.success else f"failed ({check.error or 'unknown-error'})"
    latency = f", {_format_percentless(check.latency_ms)} ms" if check.latency_ms is not None else ""
    ip_used = f", via {check.ip_used}" if check.ip_used else ""
    label = f" [{check.target.label}]" if check.target.label else ""
    return f"{check.target.host}:{check.target.port}{label}: {state}{latency}{ip_used}"


def _format_service_check(check: ServiceCheck) -> str:
    state = "ok" if check.success else f"failed ({check.error or 'unknown-error'})"
    latency = f", {_format_percentless(check.latency_ms)} ms" if check.latency_ms is not None else ""
    label = f"{check.target.label} -> " if check.target.label else ""
    return f"{label}{check.target.host}:{check.target.port}: {state}{latency}"


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


def _format_percent(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f}%"


def _format_percentless(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f}"


def _join_or_none(values: list[str]) -> str:
    return ", ".join(values) if values else "none detected"


def _yes_no_or_uncollected(collected: bool, value: bool) -> str:
    if not collected:
        return "not collected"
    return "yes" if value else "no"


def _routing_value(collected: bool, value: str | None) -> str:
    if not collected:
        return "not collected"
    return value or "none"


def _routing_observations(collected: bool, values: list[str]) -> str:
    if not collected:
        return "not collected"
    if not values:
        return "none"
    return "; ".join(values[:2]) + (" and more" if len(values) > 2 else "")


def _format_interface_mtu_summary(network) -> str:
    mtu_items = [
        f"{interface.name}={interface.mtu}"
        for interface in network.interfaces
        if interface.mtu is not None and interface.is_up
    ]
    if not mtu_items:
        mtu_items = [
            f"{interface.name}={interface.mtu}"
            for interface in network.interfaces
            if interface.mtu is not None
        ]
    return ", ".join(mtu_items[:4]) + (" and more" if len(mtu_items) > 4 else "") if mtu_items else "none detected"


def _format_arp_summary(network) -> str:
    if not network.arp_neighbors:
        return "none collected"
    interface_names = sorted(
        {
            neighbor.interface
            for neighbor in network.arp_neighbors
            if neighbor.interface
        }
    )
    if interface_names:
        return f"{len(network.arp_neighbors)} entries across {', '.join(interface_names[:3])}" + (
            " and more" if len(interface_names) > 3 else ""
        )
    return f"{len(network.arp_neighbors)} entries"
