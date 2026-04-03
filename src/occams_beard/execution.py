"""Execution-status modeling for diagnostics domains and probes."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TYPE_CHECKING

from occams_beard.defaults import DEFAULT_CHECKS
from occams_beard.models import (
    CollectedFacts,
    DiagnosticWarning,
    DnsResolutionCheck,
    DomainExecution,
    ExecutionProbe,
    ExecutionStatus,
    PingResult,
    ServiceCheck,
    TcpConnectivityCheck,
    TcpTarget,
    TraceResult,
)

if TYPE_CHECKING:
    from occams_beard.runner import DiagnosticsRunOptions


DOMAIN_LABELS = {
    "host": "Host basics",
    "resources": "Resource snapshot",
    "storage": "Storage snapshot",
    "network": "Interface inventory",
    "routing": "Routing inventory",
    "dns": "DNS checks",
    "connectivity": "Generic connectivity",
    "vpn": "VPN heuristics",
    "services": "Configured services",
}


def planned_execution_step_breakdown(options: DiagnosticsRunOptions) -> dict[str, int]:
    """Return planned probe-step counts for each domain."""

    selected_domains = set(options.selected_checks) | {"host"}
    labels_by_domain = planned_execution_step_labels(options)
    return {
        domain: (len(labels_by_domain[domain]) if domain in selected_domains else 0)
        for domain in DEFAULT_CHECKS
    }


def planned_execution_step_count(
    options: DiagnosticsRunOptions,
    *,
    domains: Iterable[str] | None = None,
) -> int:
    """Return the number of planned probe steps for selected or completed domains."""

    breakdown = planned_execution_step_breakdown(options)
    active_domains = set(domains) if domains is not None else set(breakdown)
    return sum(breakdown.get(domain, 0) for domain in active_domains)


def planned_execution_step_labels(options: DiagnosticsRunOptions) -> dict[str, list[str]]:
    """Return human-readable step labels for each planned domain."""

    return {
        domain: _planned_probe_labels_for_domain(domain, options)
        for domain in DEFAULT_CHECKS
    }


def next_execution_step_label(
    options: DiagnosticsRunOptions,
    domain: str,
    completed_steps: int,
) -> str | None:
    """Return the next in-domain step label for the active domain."""

    labels = planned_execution_step_labels(options).get(domain, [])
    if completed_steps < 0 or completed_steps >= len(labels):
        return None
    return labels[completed_steps]


def build_execution_records(
    facts: CollectedFacts,
    options: DiagnosticsRunOptions,
    warnings: list[DiagnosticWarning],
    durations_ms: dict[str, int],
    *,
    completed_domains: set[str] | None = None,
    active_domain: str | None = None,
) -> list[DomainExecution]:
    """Build structured execution records for every supported domain."""

    warnings_by_domain: dict[str, list[DiagnosticWarning]] = defaultdict(list)
    for warning in warnings:
        warnings_by_domain[warning.domain].append(warning)

    records: list[DomainExecution] = []
    selected = set(options.selected_checks)
    for domain in DEFAULT_CHECKS:
        creates_network_egress = domain in {"dns", "connectivity", "services"}
        if completed_domains is not None and domain not in completed_domains:
            if domain == "host" or domain in selected:
                records.append(
                    _not_run_record(
                        domain,
                        creates_network_egress=creates_network_egress,
                        selected=domain == "host" or domain in selected,
                        summary=(
                            "This domain is currently running."
                            if active_domain == domain
                            else "This domain is queued for the run."
                        ),
                    )
                )
            else:
                records.append(
                    _not_run_record(
                        domain,
                        creates_network_egress=creates_network_egress,
                    )
                )
            continue

        if domain == "host":
            records.append(
                _host_execution(True, facts, warnings_by_domain[domain], durations_ms.get(domain))
            )
        elif domain == "resources":
            records.append(
                _resources_execution(
                    domain in selected, facts, warnings_by_domain[domain], durations_ms.get(domain)
                )
            )
        elif domain == "storage":
            records.append(
                _storage_execution(
                    domain in selected, facts, warnings_by_domain[domain], durations_ms.get(domain)
                )
            )
        elif domain == "network":
            records.append(
                _network_execution(
                    domain in selected, facts, warnings_by_domain[domain], durations_ms.get(domain)
                )
            )
        elif domain == "routing":
            records.append(
                _routing_execution(
                    domain in selected, facts, warnings_by_domain[domain], durations_ms.get(domain)
                )
            )
        elif domain == "dns":
            records.append(
                _dns_execution(
                    domain in selected, facts, warnings_by_domain[domain], durations_ms.get(domain)
                )
            )
        elif domain == "connectivity":
            records.append(
                _connectivity_execution(
                    domain in selected,
                    facts,
                    warnings_by_domain[domain],
                    durations_ms.get(domain),
                    options,
                )
            )
        elif domain == "vpn":
            records.append(
                _vpn_execution(
                    domain in selected,
                    facts,
                    warnings_by_domain[domain],
                    durations_ms.get(domain),
                    selected_checks=selected,
                )
            )
        elif domain == "services":
            records.append(
                _services_execution(
                    domain in selected, facts, warnings_by_domain[domain], durations_ms.get(domain)
                )
            )
    return records


def _planned_probe_labels_for_domain(domain: str, options: DiagnosticsRunOptions) -> list[str]:
    if domain == "host":
        return ["Collecting endpoint identity and uptime"]
    if domain == "resources":
        return [
            "Collecting CPU and load facts",
            "Collecting memory and battery facts",
        ]
    if domain == "storage":
        return [
            "Inspecting mounted volumes",
            "Checking storage device health",
        ]
    if domain == "network":
        return [
            "Collecting interface inventory",
            "Collecting neighbor cache",
        ]
    if domain == "routing":
        return ["Collecting routing inventory"]
    if domain == "dns":
        return [
            "Reading resolver configuration",
            *[f"Resolving {hostname}" for hostname in options.dns_hosts],
        ]
    if domain == "connectivity":
        labels = [
            f"Testing TCP reachability to {_target_label(target)}"
            for target in options.targets
        ]
        if options.enable_ping:
            labels.extend(f"Pinging {target.host}" for target in options.targets)
        if options.enable_trace:
            labels.extend(f"Tracing route to {target.host}" for target in options.targets)
        return labels
    if domain == "services":
        return [f"Checking {_target_label(target)}" for target in options.targets]
    if domain == "vpn":
        return ["Checking VPN heuristics"]
    return []


def _target_label(target: TcpTarget) -> str:
    if target.label:
        return target.label
    return f"{target.host}:{target.port}"


def _host_execution(
    selected: bool,
    facts: CollectedFacts,
    warnings: list[DiagnosticWarning],
    duration_ms: int | None,
) -> DomainExecution:
    if not selected:
        return _not_run_record("host")
    details = [f"Hostname: {facts.host.hostname}.", f"Kernel: {facts.host.kernel}."]
    probe_status: ExecutionStatus = "passed"
    if warnings:
        probe_status = "partial"
    probe = ExecutionProbe(
        probe_id="host-basics",
        label="Collect host basics",
        status=probe_status,
        duration_ms=duration_ms,
        details=details,
        warnings=warnings,
    )
    return DomainExecution(
        domain="host",
        label=DOMAIN_LABELS["host"],
        status=probe_status,
        selected=True,
        duration_ms=duration_ms,
        summary="Collected endpoint identity and uptime facts as a baseline domain.",
        warnings=warnings,
        probes=[probe],
    )


def _resources_execution(
    selected: bool,
    facts: CollectedFacts,
    warnings: list[DiagnosticWarning],
    duration_ms: int | None,
) -> DomainExecution:
    if not selected:
        return _not_run_record("resources")
    cpu = facts.resources.cpu
    memory = facts.resources.memory
    resource_warnings = [
        warning for warning in warnings if warning.code != "battery-unavailable"
    ]
    battery_warnings = [warning for warning in warnings if warning.code == "battery-unavailable"]

    resource_status: ExecutionStatus = "passed"
    if resource_warnings and cpu.logical_cpus is None and memory.total_bytes is None:
        resource_status = (
            "unsupported" if _contains_warning_code(resource_warnings, "unsupported") else "failed"
        )
    elif resource_warnings:
        resource_status = "partial"

    probes = [
        ExecutionProbe(
            probe_id="resource-snapshot",
            label="Collect CPU and memory facts",
            status=resource_status,
            duration_ms=duration_ms,
            details=[
                f"Logical CPUs: {cpu.logical_cpus if cpu.logical_cpus is not None else 'unknown'}.",
                f"Memory pressure: {memory.pressure_level or 'unknown'}.",
            ],
            warnings=resource_warnings,
        ),
        _battery_probe(
            facts,
            duration_ms=duration_ms,
            warnings=battery_warnings,
        ),
    ]
    status = _aggregate_probe_statuses(probe.status for probe in probes)
    return DomainExecution(
        domain="resources",
        label=DOMAIN_LABELS["resources"],
        status=status,
        selected=True,
        duration_ms=duration_ms,
        summary="Collected local CPU, memory, and battery state when available.",
        warnings=warnings,
        probes=probes,
    )


def _storage_execution(
    selected: bool,
    facts: CollectedFacts,
    warnings: list[DiagnosticWarning],
    duration_ms: int | None,
) -> DomainExecution:
    if not selected:
        return _not_run_record("storage")
    disk_warnings = [
        warning for warning in warnings if warning.code != "storage-health-unavailable"
    ]
    health_warnings = [
        warning for warning in warnings if warning.code == "storage-health-unavailable"
    ]
    disk_status: ExecutionStatus = "passed" if facts.resources.disks else "failed"
    if disk_warnings and facts.resources.disks:
        disk_status = "partial"
    probes = [
        ExecutionProbe(
            probe_id="disk-usage",
            label="Collect disk usage",
            status=disk_status,
            duration_ms=duration_ms,
            details=[f"Volumes collected: {len(facts.resources.disks)}."],
            warnings=disk_warnings,
        ),
        _storage_device_probe(
            facts,
            duration_ms=duration_ms,
            warnings=health_warnings,
        ),
    ]
    status = _aggregate_probe_statuses(probe.status for probe in probes)
    return DomainExecution(
        domain="storage",
        label=DOMAIN_LABELS["storage"],
        status=status,
        selected=True,
        duration_ms=duration_ms,
        summary="Collected filesystem capacity and storage-device health when available.",
        warnings=warnings,
        probes=probes,
    )


def _network_execution(
    selected: bool,
    facts: CollectedFacts,
    warnings: list[DiagnosticWarning],
    duration_ms: int | None,
) -> DomainExecution:
    if not selected:
        return _not_run_record("network")

    interface_warnings = [
        warning for warning in warnings if warning.code == "interface-command-failed"
    ]
    arp_warnings = [warning for warning in warnings if warning.code == "arp-command-failed"]
    probes = [
        ExecutionProbe(
            probe_id="interface-inventory",
            label="Collect interface inventory",
            status=_status_from_collection(
                has_data=bool(facts.network.interfaces),
                warnings=interface_warnings,
                unsupported_codes={"unsupported-platform"},
            ),
            duration_ms=duration_ms,
            details=[f"Interfaces collected: {len(facts.network.interfaces)}."],
            warnings=interface_warnings,
        ),
        ExecutionProbe(
            probe_id="arp-neighbor-cache",
            label="Collect ARP or neighbor cache",
            status="passed" if not arp_warnings else "partial",
            duration_ms=duration_ms,
            details=[f"Neighbor entries collected: {len(facts.network.arp_neighbors)}."],
            warnings=arp_warnings,
        ),
    ]
    status = _aggregate_probe_statuses(probe.status for probe in probes)
    return DomainExecution(
        domain="network",
        label=DOMAIN_LABELS["network"],
        status=status,
        selected=True,
        duration_ms=duration_ms,
        summary="Collected interface state, local addresses, and neighbor context.",
        warnings=warnings,
        probes=probes,
    )


def _routing_execution(
    selected: bool,
    facts: CollectedFacts,
    warnings: list[DiagnosticWarning],
    duration_ms: int | None,
) -> DomainExecution:
    if not selected:
        return _not_run_record("routing")
    status = _status_from_collection(
        has_data=bool(
            facts.network.route_summary.routes or facts.network.route_summary.has_default_route
        ),
        warnings=warnings,
        unsupported_codes={"unsupported-platform"},
    )
    if _contains_warning_code(warnings, "route-data-warning") and status == "passed":
        status = "partial"
    probe = ExecutionProbe(
        probe_id="route-inventory",
        label="Collect routing summary",
        status=status,
        duration_ms=duration_ms,
        details=[
            (
                "Default route present: "
                f"{'yes' if facts.network.route_summary.has_default_route else 'no'}."
            ),
            f"Default route state: {facts.network.route_summary.default_route_state}.",
        ],
        warnings=warnings,
    )
    return DomainExecution(
        domain="routing",
        label=DOMAIN_LABELS["routing"],
        status=status,
        selected=True,
        duration_ms=duration_ms,
        summary="Collected route table and default-route interpretation.",
        warnings=warnings,
        probes=[probe],
    )


def _dns_execution(
    selected: bool,
    facts: CollectedFacts,
    warnings: list[DiagnosticWarning],
    duration_ms: int | None,
) -> DomainExecution:
    if not selected:
        return _not_run_record("dns", creates_network_egress=True)

    probes: list[ExecutionProbe] = [
        ExecutionProbe(
            probe_id="resolver-inventory",
            label="Determine configured resolvers",
            status="passed" if facts.dns.resolvers else "partial",
            duration_ms=duration_ms,
            details=[
                (
                    f"Resolvers: {', '.join(facts.dns.resolvers[:3])}."
                    if facts.dns.resolvers
                    else "Resolver inventory was not available."
                )
            ],
            warnings=[warning for warning in warnings if warning.code == "resolver-unavailable"],
        )
    ]
    probes.extend(_dns_probe(check) for check in facts.dns.checks)
    status = _aggregate_probe_statuses(probe.status for probe in probes)
    return DomainExecution(
        domain="dns",
        label=DOMAIN_LABELS["dns"],
        status=status,
        selected=True,
        duration_ms=duration_ms,
        summary="Collected resolver configuration and hostname resolution checks.",
        warnings=warnings,
        probes=probes,
        creates_network_egress=True,
    )


def _connectivity_execution(
    selected: bool,
    facts: CollectedFacts,
    warnings: list[DiagnosticWarning],
    duration_ms: int | None,
    options: DiagnosticsRunOptions,
) -> DomainExecution:
    if not selected:
        return _not_run_record("connectivity", creates_network_egress=True)

    probes: list[ExecutionProbe] = [_tcp_probe(check) for check in facts.connectivity.tcp_checks]
    for target in options.targets:
        if options.enable_ping:
            ping_result = next(
                (item for item in facts.connectivity.ping_checks if item.target == target.host),
                None,
            )
            if ping_result is not None:
                probes.append(_ping_probe(ping_result))
        else:
            probes.append(
                ExecutionProbe(
                    probe_id=f"ping:{target.host}",
                    label=f"Ping {target.host}",
                    status="skipped",
                    target=target.host,
                    details=["Ping was not enabled for this run."],
                    creates_network_egress=True,
                )
            )

        if options.enable_trace:
            trace_result = next(
                (item for item in facts.connectivity.trace_results if item.target == target.host),
                None,
            )
            if trace_result is not None:
                probes.append(_trace_probe(trace_result))
        else:
            probes.append(
                ExecutionProbe(
                    probe_id=f"trace:{target.host}",
                    label=f"Trace {target.host}",
                    status="skipped",
                    target=target.host,
                    details=["Traceroute was not enabled for this run."],
                    creates_network_egress=True,
                )
            )

    status = _aggregate_probe_statuses(
        probe.status for probe in probes if probe.probe_id.startswith(("tcp:", "ping:", "trace:"))
    )
    if (
        _contains_warning_code(warnings, "trace-target-resolution-timeout")
        and status != "unsupported"
    ):
        status = "partial"
    return DomainExecution(
        domain="connectivity",
        label=DOMAIN_LABELS["connectivity"],
        status=status,
        selected=True,
        duration_ms=duration_ms,
        summary=(
            "Collected generic DNS-independent and TCP path checks."
            if facts.connectivity.tcp_checks
            else "No generic connectivity probes were collected."
        ),
        warnings=warnings,
        probes=probes,
        creates_network_egress=True,
    )


def _services_execution(
    selected: bool,
    facts: CollectedFacts,
    warnings: list[DiagnosticWarning],
    duration_ms: int | None,
) -> DomainExecution:
    if not selected:
        return _not_run_record("services", creates_network_egress=True)
    probes = [_service_probe(check) for check in facts.services.checks]
    status = _aggregate_probe_statuses(probe.status for probe in probes)
    return DomainExecution(
        domain="services",
        label=DOMAIN_LABELS["services"],
        status=status,
        selected=True,
        duration_ms=duration_ms,
        summary="Collected TCP checks for intended service targets.",
        warnings=warnings,
        probes=probes,
        creates_network_egress=True,
    )


def _vpn_execution(
    selected: bool,
    facts: CollectedFacts,
    warnings: list[DiagnosticWarning],
    duration_ms: int | None,
    *,
    selected_checks: set[str],
) -> DomainExecution:
    if not selected:
        return _not_run_record("vpn")

    status: ExecutionStatus = "passed"
    details: list[str] = []
    if "network" not in selected_checks or "routing" not in selected_checks:
        status = "partial"
        details.append("VPN heuristics ran without both network and routing domains selected.")
    if facts.vpn.signals:
        details.extend(
            (
                f"VPN signal matched interface {signal.interface_name} with "
                f"confidence {signal.confidence:.2f}."
            )
            for signal in facts.vpn.signals
        )
    else:
        details.append("No VPN-like interfaces or default-route tunnel hints were detected.")
    probe = ExecutionProbe(
        probe_id="vpn-heuristics",
        label="Evaluate VPN and tunnel signals",
        status=status,
        duration_ms=duration_ms,
        details=details,
        warnings=warnings,
    )
    return DomainExecution(
        domain="vpn",
        label=DOMAIN_LABELS["vpn"],
        status=status,
        selected=True,
        duration_ms=duration_ms,
        summary="Evaluated tunnel-interface and route heuristics.",
        warnings=warnings,
        probes=[probe],
    )


def _dns_probe(check: DnsResolutionCheck) -> ExecutionProbe:
    if check.error == "hostname-resolution-timeout":
        status: ExecutionStatus = "partial"
        detail = "Lookup timed out before a resolver answer was returned."
    else:
        status = "passed" if check.success else "failed"
        detail = (
            f"Resolved to {', '.join(check.resolved_addresses[:3])}."
            if check.success and check.resolved_addresses
            else f"Lookup failed: {check.error or 'unknown-error'}."
        )
    return ExecutionProbe(
        probe_id=f"dns:{check.hostname}",
        label=f"Resolve {check.hostname}",
        status=status,
        duration_ms=check.duration_ms,
        target=check.hostname,
        details=[detail],
        creates_network_egress=True,
    )


def _tcp_probe(check: TcpConnectivityCheck) -> ExecutionProbe:
    return ExecutionProbe(
        probe_id=f"tcp:{check.target.host}:{check.target.port}",
        label=f"TCP {check.target.host}:{check.target.port}",
        status="passed" if check.success else "failed",
        duration_ms=check.duration_ms,
        target=f"{check.target.host}:{check.target.port}",
        details=[
            (
                f"Connected in {check.latency_ms:.1f} ms."
                if check.success and check.latency_ms is not None
                else f"TCP connection failed: {check.error or 'unknown-error'}."
            )
        ],
        creates_network_egress=True,
    )


def _ping_probe(result: PingResult) -> ExecutionProbe:
    status: ExecutionStatus
    if result.error == "ping-command-unavailable":
        status = "unsupported"
    else:
        status = "passed" if result.success else "failed"
    return ExecutionProbe(
        probe_id=f"ping:{result.target}",
        label=f"Ping {result.target}",
        status=status,
        duration_ms=result.duration_ms,
        target=result.target,
        details=[
            (
                f"Average latency {result.average_latency_ms:.1f} ms, packet "
                f"loss {result.packet_loss_percent:.1f}%."
                if result.success
                and result.average_latency_ms is not None
                and result.packet_loss_percent is not None
                else f"Ping failed: {result.error or 'unknown-error'}."
            )
        ],
        creates_network_egress=True,
    )


def _trace_probe(result: TraceResult) -> ExecutionProbe:
    if result.error == "trace-command-unavailable":
        status: ExecutionStatus = "unsupported"
    elif result.partial:
        status = "partial"
    elif result.success:
        status = "passed"
    else:
        status = "failed"
    return ExecutionProbe(
        probe_id=f"trace:{result.target}",
        label=f"Trace {result.target}",
        status=status,
        duration_ms=result.duration_ms,
        target=result.target,
        details=[
            (
                f"Trace reached {result.target_address or result.target} in "
                f"{len(result.hops)} hop(s)."
                if result.success
                else (
                    f"Trace reached only hop {result.last_responding_hop} before stopping."
                    if result.partial and result.last_responding_hop is not None
                    else f"Trace failed: {result.error or 'unknown-error'}."
                )
            )
        ],
        creates_network_egress=True,
    )


def _service_probe(check: ServiceCheck) -> ExecutionProbe:
    return ExecutionProbe(
        probe_id=f"service:{check.target.host}:{check.target.port}",
        label=f"Service {check.target.label or check.target.host}:{check.target.port}",
        status="passed" if check.success else "failed",
        duration_ms=check.duration_ms,
        target=f"{check.target.host}:{check.target.port}",
        details=[
            (
                f"Connected in {check.latency_ms:.1f} ms."
                if check.success and check.latency_ms is not None
                else f"Service path failed: {check.error or 'unknown-error'}."
            )
        ],
        creates_network_egress=True,
    )


def _battery_probe(
    facts: CollectedFacts,
    *,
    duration_ms: int | None,
    warnings: list[DiagnosticWarning],
) -> ExecutionProbe:
    battery = facts.resources.battery
    if warnings:
        status: ExecutionStatus = "partial"
        details = ["Battery health facts could not be collected on this endpoint."]
    elif battery is None:
        status = "skipped"
        details = ["Battery health was not collected in this run."]
    elif not battery.present:
        status = "skipped"
        details = ["No local battery was detected on this endpoint."]
    else:
        status = "passed"
        details = [
            (
                "Battery state: "
                f"{battery.charge_percent if battery.charge_percent is not None else 'unknown'}% "
                f"{battery.status or 'status-unknown'}."
            ),
            (
                f"Battery condition: {battery.condition}."
                if battery.condition
                else "Battery condition was not reported."
            ),
        ]
    return ExecutionProbe(
        probe_id="battery-health",
        label="Collect battery health",
        status=status,
        duration_ms=duration_ms,
        details=details,
        warnings=warnings,
    )


def _storage_device_probe(
    facts: CollectedFacts,
    *,
    duration_ms: int | None,
    warnings: list[DiagnosticWarning],
) -> ExecutionProbe:
    storage_devices = facts.resources.storage_devices
    if warnings:
        status: ExecutionStatus = "partial"
        details = ["Storage-device health facts could not be collected on this endpoint."]
    elif storage_devices:
        status = "passed"
        notable_statuses = ", ".join(
            filter(
                None,
                (
                    f"{device.device_id}="
                    f"{device.health_status or device.operational_status or 'unknown'}"
                    for device in storage_devices[:3]
                ),
            )
        )
        details = [
            f"Storage devices collected: {len(storage_devices)}.",
            (
                f"Reported health states: {notable_statuses}."
                if notable_statuses
                else "No storage-device health status strings were reported."
            ),
        ]
    else:
        status = "skipped"
        details = ["No storage-device health facts were exposed on this endpoint."]
    return ExecutionProbe(
        probe_id="storage-device-health",
        label="Collect storage-device health",
        status=status,
        duration_ms=duration_ms,
        details=details,
        warnings=warnings,
    )


def _status_from_collection(
    *,
    has_data: bool,
    warnings: list[DiagnosticWarning],
    unsupported_codes: set[str],
) -> ExecutionStatus:
    if not warnings:
        return "passed" if has_data else "failed"
    if _contains_warning_code(warnings, *unsupported_codes) and not has_data:
        return "unsupported"
    if has_data:
        return "partial"
    return "failed"


def _aggregate_probe_statuses(statuses: Iterable[ExecutionStatus]) -> ExecutionStatus:
    normalized = [status for status in statuses if status not in {"skipped", "not_run"}]
    if not normalized:
        return "skipped"
    unique = set(normalized)
    if unique == {"passed"}:
        return "passed"
    if unique == {"failed"}:
        return "failed"
    if unique == {"unsupported"}:
        return "unsupported"
    if "partial" in unique:
        return "partial"
    if "failed" in unique and "passed" in unique:
        return "partial"
    if "unsupported" in unique and len(unique) > 1:
        return "partial"
    return "partial"


def _contains_warning_code(warnings: list[DiagnosticWarning], *fragments: str) -> bool:
    return any(any(fragment in warning.code for fragment in fragments) for warning in warnings)


def _not_run_record(
    domain: str,
    *,
    creates_network_egress: bool = False,
    selected: bool = False,
    summary: str | None = None,
) -> DomainExecution:
    return DomainExecution(
        domain=domain,
        label=DOMAIN_LABELS[domain],
        status="not_run",
        selected=selected,
        summary=summary or "This domain was not selected for the run.",
        creates_network_egress=creates_network_egress,
    )
