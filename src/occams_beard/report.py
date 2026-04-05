"""Human-readable report rendering."""

from __future__ import annotations

from occams_beard.models import (
    EndpointDiagnosticResult,
    Finding,
    ServiceCheck,
    TcpConnectivityCheck,
)
from occams_beard.storage_policy import (
    capacity_group_label,
    capacity_group_representative,
    distinct_capacity_groups,
    is_zero_capacity_pseudo_mount,
)


def render_report(result: EndpointDiagnosticResult, json_path: str | None = None) -> str:
    """Render a concise human-readable diagnostic report."""

    host = result.facts.host
    resources = result.facts.resources
    network = result.facts.network
    top_finding = result.findings[0] if result.findings else None
    selected_checks = set(result.metadata.selected_checks)
    guided = result.guided_experience
    platform_summary = (
        f"{result.platform.system} {result.platform.release} ({result.platform.machine})"
    )
    internet_reachable = _yes_no_or_uncollected(
        "connectivity" in selected_checks,
        result.facts.connectivity.internet_reachable,
    )
    default_route_present = _yes_no_or_uncollected(
        "routing" in selected_checks,
        network.route_summary.has_default_route,
    )
    uptime_seconds = host.uptime_seconds if host.uptime_seconds is not None else "unknown"
    logical_cpus = (
        resources.cpu.logical_cpus if resources.cpu.logical_cpus is not None else "unknown"
    )
    cpu_utilization = _format_percent(resources.cpu.utilization_percent_estimate)
    cpu_saturation = resources.cpu.saturation_level or "unknown"
    swap_summary = _swap_summary(collected="resources" in selected_checks, resources=resources)
    process_summary = _process_summary(
        collected="resources" in selected_checks,
        resources=resources,
    )
    time_summary = _time_summary(
        collected="time" in selected_checks,
        time_state=result.facts.time,
    )
    time_skew_summary = _time_skew_summary(
        collected="time" in selected_checks,
        time_state=result.facts.time,
    )
    active_interfaces = (
        _join_or_none(network.active_interfaces)
        if "network" in selected_checks
        else "not collected"
    )
    battery_summary = _battery_summary(
        collected="resources" in selected_checks,
        battery=resources.battery,
    )
    volume_summary = _volume_summary(
        collected="storage" in selected_checks,
        resources=resources,
    )
    storage_device_summary = _storage_device_summary(
        collected="storage" in selected_checks,
        resources=resources,
    )
    local_addresses = (
        _join_or_none(network.local_addresses) if "network" in selected_checks else "not collected"
    )
    interface_mtus = (
        _format_interface_mtu_summary(network) if "network" in selected_checks else "not collected"
    )
    arp_summary = _format_arp_summary(network) if "network" in selected_checks else "not collected"
    default_gateway = _routing_value(
        "routing" in selected_checks,
        network.route_summary.default_gateway,
    )
    default_interface = _routing_value(
        "routing" in selected_checks,
        network.route_summary.default_interface,
    )
    default_route_state = _routing_value(
        "routing" in selected_checks,
        network.route_summary.default_route_state,
    )
    route_count = (
        len(network.route_summary.routes) if "routing" in selected_checks else "not collected"
    )
    route_observations = _routing_observations(
        "routing" in selected_checks,
        network.route_summary.observations,
    )

    lines = [
        "Occam's Beard Report",
        "================================",
        "",
        "Summary",
        f"- Result schema version: {result.schema_version}",
        f"- App version: {result.metadata.version}",
        f"- Host: {host.hostname}",
        f"- Platform: {platform_summary}",
        f"- Internet reachable: {internet_reachable}",
        f"- Default route present: {default_route_present}",
        f"- Probable fault domain: {result.probable_fault_domain}",
    ]

    if top_finding:
        lines.append(
            f"- Fault-domain basis: {top_finding.title} ({top_finding.confidence:.2f} confidence)"
        )

    if result.metadata.profile_id:
        lines.append(
            "- Profile: "
            f"{result.metadata.profile_name or result.metadata.profile_id} "
            f"({result.metadata.issue_category or 'unspecified issue category'})"
        )

    lines.extend(
        [
            "",
            "Execution Status",
        ]
    )

    for record in result.execution:
        if not record.selected:
            continue
        lines.extend(_render_execution_record(record))

    lines.extend(
        [
            "",
            "Key Findings",
        ]
    )

    for index, finding in enumerate(result.findings[:5], start=1):
        lines.extend(_render_finding(index, finding))

    if guided is not None:
        if guided.what_we_know:
            lines.extend(["", "What We Know"])
            for item in guided.what_we_know:
                lines.append(f"- {item}")
        if guided.likely_happened:
            lines.extend(["", "What Likely Happened"])
            for item in guided.likely_happened:
                lines.append(f"- {item}")
        if guided.safe_next_steps:
            lines.extend(["", "What You Can Try Safely"])
            for item in guided.safe_next_steps:
                lines.append(f"- {item}")
        if guided.escalation_guidance:
            lines.extend(["", "Escalate When"])
            for item in guided.escalation_guidance:
                lines.append(f"- {item}")
        if guided.uncertainty_notes:
            lines.extend(["", "What Remains Uncertain"])
            for item in guided.uncertainty_notes:
                lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "System Snapshot",
            f"- Current user: {host.current_user or 'unknown'}",
            f"- Uptime (seconds): {uptime_seconds}",
            f"- CPU logical cores: {logical_cpus}",
            f"- CPU utilization estimate: {cpu_utilization}",
            f"- CPU saturation: {cpu_saturation}",
            f"- Memory pressure: {resources.memory.pressure_level or 'unknown'}",
            (
                "- Memory available: "
                f"{_format_bytes(resources.memory.available_bytes)} / "
                f"{_format_bytes(resources.memory.total_bytes)}"
            ),
            (
                f"- Memory available percent: {_format_percent(resources.memory.available_percent)}"
            ),
            f"- Swap or commit pressure: {swap_summary}",
            f"- Bounded process hints: {process_summary}",
            f"- Battery health: {battery_summary}",
            "",
            "Time Snapshot",
            f"- Local time state: {time_summary}",
            f"- Clock skew check: {time_skew_summary}",
            "",
            "Storage Snapshot",
            f"- Monitored volumes: {volume_summary}",
            f"- Storage device health: {storage_device_summary}",
            "",
            "Network Snapshot",
            f"- Active interfaces: {active_interfaces}",
            f"- Local addresses: {local_addresses}",
            f"- Interface MTUs: {interface_mtus}",
            f"- ARP neighbors: {arp_summary}",
            f"- Default gateway: {default_gateway}",
            f"- Default interface: {default_interface}",
            f"- Default route state: {default_route_state}",
            f"- Route entries collected: {route_count}",
            f"- Route observations: {route_observations}",
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
            latency = (
                f", avg {_format_percentless(ping.average_latency_ms)} ms"
                if ping.average_latency_ms is not None
                else ""
            )
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
        for dns_check in result.facts.dns.checks:
            if dns_check.success:
                detail = (
                    ", ".join(dns_check.resolved_addresses[:3])
                    if dns_check.resolved_addresses
                    else "resolved"
                )
                lines.append(f"- {dns_check.hostname}: ok ({detail})")
            elif dns_check.error == "hostname-resolution-timeout":
                lines.append(f"- {dns_check.hostname}: partial (lookup timed out)")
            else:
                lines.append(
                    f"- {dns_check.hostname}: failed ({dns_check.error or 'unknown-error'})"
                )
    else:
        lines.append("- No DNS checks were collected.")

    lines.extend(["", "Configured Service Checks"])
    if "services" not in selected_checks:
        lines.append("- Service checks were not collected.")
    elif result.facts.services.checks:
        for service_check in result.facts.services.checks:
            lines.append(f"- {_format_service_check(service_check)}")
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
        for warning in _dedupe_warnings(result.warnings):
            lines.append(f"- [{warning.domain}:{warning.code}] {warning.message}")

    return "\n".join(lines)


def _render_finding(index: int, finding: Finding) -> list[str]:
    lines = [
        f"{index}. [{finding.severity.upper()}] {finding.title}",
        f"   Derived finding: {finding.summary}",
    ]
    if finding.plain_language:
        lines.append(f"   Plain language: {finding.plain_language}")
    if finding.evidence_summary:
        lines.append(f"   Evidence summary: {finding.evidence_summary}")
    for evidence in finding.evidence[:3]:
        lines.append(f"   Observed fact: {evidence}")
    if len(finding.evidence) > 3:
        lines.append(
            f"   Observed fact: {len(finding.evidence) - 3} more supporting signal(s) not shown"
        )
    if finding.heuristic:
        lines.append(f"   Heuristic conclusion: {finding.probable_cause}")
    else:
        lines.append(f"   Probable cause: {finding.probable_cause}")
    if finding.safe_next_actions:
        lines.append(f"   Safe next actions: {'; '.join(finding.safe_next_actions[:2])}")
    if finding.escalation_triggers:
        lines.append(f"   Escalate when: {'; '.join(finding.escalation_triggers[:2])}")
    if finding.uncertainty_notes:
        lines.append(f"   Uncertainty: {'; '.join(finding.uncertainty_notes[:2])}")
    lines.append(
        f"   Fault domain: {finding.fault_domain} "
        f"({finding.confidence:.2f} confidence, "
        f"{'heuristic' if finding.heuristic else 'evidence-based'})"
    )
    return lines


def _render_execution_record(record) -> list[str]:
    summary = record.summary or "No execution summary recorded."
    egress = "network egress" if record.creates_network_egress else "local only"
    lines = [f"- {record.label}: {record.status} ({egress})"]
    if record.duration_ms is not None:
        lines.append(f"  Duration: {record.duration_ms} ms")
    lines.append(f"  Summary: {summary}")
    for warning in record.warnings[:2]:
        lines.append(f"  Warning: [{warning.domain}:{warning.code}] {warning.message}")
    partial_probes = [
        probe
        for probe in record.probes
        if probe.status in {"failed", "partial", "unsupported", "skipped"}
    ]
    for probe in partial_probes[:2]:
        detail = probe.details[0] if probe.details else "No details recorded."
        lines.append(f"  Probe {probe.label}: {probe.status} ({detail})")
    return lines


def _format_tcp_check(check: TcpConnectivityCheck) -> str:
    state = "ok" if check.success else f"failed ({check.error or 'unknown-error'})"
    latency = (
        f", {_format_percentless(check.latency_ms)} ms" if check.latency_ms is not None else ""
    )
    ip_used = f", via {check.ip_used}" if check.ip_used else ""
    label = f" [{check.target.label}]" if check.target.label else ""
    return f"{check.target.host}:{check.target.port}{label}: {state}{latency}{ip_used}"


def _format_service_check(check: ServiceCheck) -> str:
    state = "ok" if check.success else f"failed ({check.error or 'unknown-error'})"
    latency = (
        f", {_format_percentless(check.latency_ms)} ms" if check.latency_ms is not None else ""
    )
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


def _format_utc_offset(offset_minutes: int | None) -> str:
    if offset_minutes is None:
        return "unknown"
    sign = "+" if offset_minutes >= 0 else "-"
    total_minutes = abs(offset_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def _battery_summary(*, collected: bool, battery) -> str:
    if not collected:
        return "not collected"
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
    if battery.cycle_count is not None:
        parts.append(f"{battery.cycle_count} cycles")
    return ", ".join(parts) if parts else "present"


def _time_summary(*, collected: bool, time_state) -> str:
    if not collected:
        return "not collected"
    if time_state is None:
        return "unavailable"
    identifier_part = (
        f"{time_state.timezone_identifier} ({time_state.timezone_identifier_source})"
        if time_state.timezone_identifier is not None
        else "identifier unavailable"
    )
    offset_part = (
        _format_utc_offset(time_state.utc_offset_minutes)
        if time_state.utc_offset_minutes is not None
        else "offset unknown"
    )
    return (
        f"{time_state.local_time_iso}, {time_state.timezone_name or 'timezone unknown'}, "
        f"{identifier_part}, {offset_part}"
    )


def _time_skew_summary(*, collected: bool, time_state) -> str:
    if not collected:
        return "not collected"
    if time_state is None or time_state.skew_check is None:
        return "unavailable"
    skew_check = time_state.skew_check
    if skew_check.status == "not_run":
        return "not enabled"
    if skew_check.status != "checked":
        return f"inconclusive ({skew_check.error or 'unknown-error'})"
    return (
        f"{skew_check.skew_seconds:.1f}s vs {skew_check.reference_label} "
        f"({skew_check.absolute_skew_seconds:.1f}s absolute)"
    )


def _volume_summary(*, collected: bool, resources) -> str:
    if not collected:
        return "not collected"
    if not resources.disks:
        return "none collected"
    items = []
    for group in distinct_capacity_groups(resources.disks)[:4]:
        disk = capacity_group_representative(group)
        if disk.free_percent is not None:
            items.append(
                f"{capacity_group_label(group)} "
                f"({disk.percent_used:.1f}% used, "
                f"{disk.free_percent:.1f}% free, "
                f"{disk.pressure_level or 'unknown'} pressure)"
            )
        else:
            items.append(f"{capacity_group_label(group)} ({disk.percent_used:.1f}% used)")
    pseudo_mounts = [disk.path for disk in resources.disks if is_zero_capacity_pseudo_mount(disk)]
    if pseudo_mounts:
        items.append(
            "non-capacity pseudo-mounts: "
            + ", ".join(pseudo_mounts[:2])
            + (" and more" if len(pseudo_mounts) > 2 else "")
        )
    return ", ".join(items)


def _storage_device_summary(*, collected: bool, resources) -> str:
    if not collected:
        return "not collected"
    if not resources.storage_devices:
        return "none exposed"
    if not any(
        device.health_status or device.operational_status
        for device in resources.storage_devices
    ):
        return "inventory only (no health state exposed)"
    return ", ".join(
        (
            f"{device.device_id}="
            f"{device.health_status or device.operational_status or 'unknown'}"
        )
        for device in resources.storage_devices[:4]
    )


def _swap_summary(*, collected: bool, resources) -> str:
    if not collected:
        return "not collected"

    memory = resources.memory
    parts = []
    if memory.swap_used_bytes is not None or memory.swap_total_bytes is not None:
        parts.append(
            "swap "
            f"{_format_bytes(memory.swap_used_bytes)} / {_format_bytes(memory.swap_total_bytes)}"
        )
    if memory.commit_pressure_level is not None:
        parts.append(f"commit pressure {memory.commit_pressure_level}")
    elif memory.committed_bytes is not None and memory.commit_limit_bytes is not None:
        parts.append(
            "commit "
            f"{_format_bytes(memory.committed_bytes)} / {_format_bytes(memory.commit_limit_bytes)}"
        )
    return ", ".join(parts) if parts else "not exposed"


def _process_summary(*, collected: bool, resources) -> str:
    if not collected:
        return "not collected"

    snapshot = resources.process_snapshot
    if snapshot is None:
        return "unavailable"
    if not snapshot.top_categories:
        return f"sampled {snapshot.sampled_process_count}, no notable categories retained"

    category_parts = []
    for item in snapshot.top_categories[:3]:
        cpu_part = (
            f"{_format_percent(item.combined_cpu_percent_estimate)} CPU"
            if item.combined_cpu_percent_estimate is not None
            else "CPU not exposed"
        )
        memory_part = (
            _format_bytes(item.combined_memory_bytes)
            if item.combined_memory_bytes is not None
            else "memory unknown"
        )
        category_parts.append(
            f"{_process_category_label(item.category)} "
            f"({item.process_count}, {cpu_part}, {memory_part})"
        )
    return "; ".join(category_parts)


def _process_category_label(value: str) -> str:
    return {
        "browser": "browser",
        "collaboration": "collaboration apps",
        "container_runtime": "container runtime",
        "database": "database",
        "ide": "IDE or editor",
        "other": "other processes",
        "vm": "VM",
    }.get(value, value.replace("_", " "))


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
    return (
        ", ".join(mtu_items[:4]) + (" and more" if len(mtu_items) > 4 else "")
        if mtu_items
        else "none detected"
    )


def _format_arp_summary(network) -> str:
    if not network.arp_neighbors:
        return "none collected"
    interface_names = sorted(
        {neighbor.interface for neighbor in network.arp_neighbors if neighbor.interface}
    )
    if interface_names:
        return f"{len(network.arp_neighbors)} entries across {', '.join(interface_names[:3])}" + (
            " and more" if len(interface_names) > 3 else ""
        )
    return f"{len(network.arp_neighbors)} entries"


def _dedupe_warnings(warnings):
    seen = set()
    ordered = []
    for warning in warnings:
        key = (warning.domain, warning.code, warning.message)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(warning)
    return ordered
