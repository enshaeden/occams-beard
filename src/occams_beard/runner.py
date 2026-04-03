"""Shared diagnostics execution service for CLI and local app flows."""

from __future__ import annotations

import logging
import platform as python_platform
import time
from dataclasses import dataclass
from typing import Iterable

from occams_beard import __version__
from occams_beard.collectors.connectivity import collect_connectivity_state
from occams_beard.collectors.dns import collect_dns_state
from occams_beard.collectors.network import collect_network_state
from occams_beard.collectors.routing import collect_route_summary
from occams_beard.collectors.services import collect_service_state
from occams_beard.collectors.storage import collect_storage_state
from occams_beard.collectors.system import collect_host_basics, collect_resource_state
from occams_beard.collectors.vpn import collect_vpn_state
from occams_beard.defaults import (
    ALLOWED_CHECKS,
    DEFAULT_CHECKS,
    DEFAULT_DNS_HOSTS,
    DEFAULT_TCP_TARGETS,
)
from occams_beard.findings import evaluate_selected_findings
from occams_beard.models import (
    CollectedFacts,
    CpuState,
    EndpointDiagnosticResult,
    MemoryState,
    Metadata,
    PlatformInfo,
    ResourceState,
    RouteSummary,
    TcpTarget,
)
from occams_beard.utils.time import utc_now_iso
from occams_beard.utils.validation import (
    parse_check_selection,
    resolve_dns_hosts,
    resolve_tcp_targets,
)


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DiagnosticsRunOptions:
    """Validated operator-selected options for a diagnostics run."""

    selected_checks: list[str]
    targets: list[TcpTarget]
    dns_hosts: list[str]
    enable_ping: bool = False
    enable_trace: bool = False


def build_run_options(
    *,
    checks: str | None = None,
    targets: Iterable[str] | None = None,
    target_file: str | None = None,
    dns_hosts: Iterable[str] | None = None,
    enable_ping: bool = False,
    enable_trace: bool = False,
) -> DiagnosticsRunOptions:
    """Build validated run options from operator-facing input values."""

    return DiagnosticsRunOptions(
        selected_checks=parse_check_selection(
            checks,
            allowed_checks=ALLOWED_CHECKS,
            default_checks=DEFAULT_CHECKS,
        ),
        targets=resolve_tcp_targets(
            list(targets or []),
            target_file,
            default_targets=DEFAULT_TCP_TARGETS,
        ),
        dns_hosts=resolve_dns_hosts(list(dns_hosts or []), default_hosts=DEFAULT_DNS_HOSTS),
        enable_ping=enable_ping,
        enable_trace=enable_trace,
    )


def run_diagnostics(options: DiagnosticsRunOptions) -> EndpointDiagnosticResult:
    """Execute diagnostics for the provided validated options."""

    start = time.perf_counter()
    warnings = []

    LOGGER.info("Running host and network diagnostics for checks: %s", ", ".join(options.selected_checks))
    LOGGER.debug(
        "Diagnostics input summary: tcp_targets=%d dns_hosts=%d enable_ping=%s enable_trace=%s",
        len(options.targets),
        len(options.dns_hosts),
        options.enable_ping,
        options.enable_trace,
    )

    host, host_warnings = collect_host_basics()
    warnings.extend(host_warnings)

    if "resources" in options.selected_checks:
        cpu_state, memory_state, resource_warnings = collect_resource_state()
        warnings.extend(resource_warnings)
    else:
        cpu_state, memory_state = _empty_resource_components()

    disks, storage_warnings = (
        collect_storage_state() if "storage" in options.selected_checks else ([], [])
    )
    warnings.extend(storage_warnings)
    resources = ResourceState(cpu=cpu_state, memory=memory_state, disks=disks)

    network_state, network_warnings = (
        collect_network_state() if "network" in options.selected_checks else (_empty_network_state(), [])
    )
    warnings.extend(network_warnings)

    route_summary, route_warnings = (
        collect_route_summary()
        if "routing" in options.selected_checks
        else (RouteSummary(None, None, False, []), [])
    )
    warnings.extend(route_warnings)
    network_state.route_summary = route_summary

    dns_state, dns_warnings = (
        collect_dns_state(options.dns_hosts)
        if "dns" in options.selected_checks
        else (_empty_dns_state(), [])
    )
    warnings.extend(dns_warnings)

    connectivity_state, connectivity_warnings = (
        collect_connectivity_state(
            targets=options.targets,
            enable_ping=options.enable_ping,
            enable_trace=options.enable_trace,
        )
        if "connectivity" in options.selected_checks
        else (_empty_connectivity_state(), [])
    )
    warnings.extend(connectivity_warnings)

    service_state = (
        collect_service_state(options.targets)
        if "services" in options.selected_checks
        else _empty_service_state()
    )
    vpn_state = (
        collect_vpn_state(network_state, route_summary)
        if "vpn" in options.selected_checks
        else _empty_vpn_state()
    )

    facts = CollectedFacts(
        host=host,
        resources=resources,
        network=network_state,
        dns=dns_state,
        connectivity=connectivity_state,
        vpn=vpn_state,
        services=service_state,
    )
    findings, probable_fault_domain = evaluate_selected_findings(facts, options.selected_checks)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    return EndpointDiagnosticResult(
        metadata=Metadata(
            project_name="occams-beard",
            version=__version__,
            generated_at=utc_now_iso(),
            elapsed_ms=elapsed_ms,
            selected_checks=options.selected_checks,
        ),
        platform=PlatformInfo(
            system=python_platform.system(),
            release=python_platform.release(),
            version=python_platform.version(),
            machine=python_platform.machine(),
            python_version=python_platform.python_version(),
        ),
        facts=facts,
        findings=findings,
        probable_fault_domain=probable_fault_domain,
        warnings=warnings,
    )


def _empty_network_state():
    from occams_beard.models import NetworkState

    return NetworkState()


def _empty_dns_state():
    from occams_beard.models import DnsState

    return DnsState()


def _empty_connectivity_state():
    from occams_beard.models import ConnectivityState

    return ConnectivityState(internet_reachable=False)


def _empty_service_state():
    from occams_beard.models import ServiceState

    return ServiceState()


def _empty_vpn_state():
    from occams_beard.models import VpnState

    return VpnState()


def _empty_resource_components() -> tuple[CpuState, MemoryState]:
    return CpuState(logical_cpus=None), MemoryState(
        total_bytes=None,
        available_bytes=None,
        free_bytes=None,
        pressure_level=None,
    )
