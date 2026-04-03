"""Shared diagnostics execution service for CLI and local app flows."""

from __future__ import annotations

import logging
import platform as python_platform
import time
from collections.abc import Callable, Iterable
from contextlib import nullcontext
from dataclasses import dataclass
from typing import cast

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
from occams_beard.execution import (
    build_execution_records,
    planned_execution_step_breakdown,
    planned_execution_step_count,
)
from occams_beard.findings import evaluate_selected_findings
from occams_beard.models import (
    BatteryState,
    CollectedFacts,
    CpuState,
    DiagnosticProfile,
    DiagnosticWarning,
    DiskVolume,
    DomainExecution,
    EndpointDiagnosticResult,
    FaultDomain,
    MemoryState,
    Metadata,
    PlatformInfo,
    RawCommandCapture,
    ResourceState,
    RouteSummary,
    StorageDeviceHealth,
    TcpTarget,
)
from occams_beard.profile_catalog import get_profile
from occams_beard.schema import RESULT_SCHEMA_VERSION
from occams_beard.utils.subprocess import capture_command_output
from occams_beard.utils.time import utc_now_iso
from occams_beard.utils.validation import (
    parse_check_selection,
    resolve_dns_hosts,
    resolve_tcp_targets,
)

LOGGER = logging.getLogger(__name__)
ProgressCallback = Callable[[list[DomainExecution], str | None, int, int, dict[str, int]], None]


@dataclass(slots=True)
class DiagnosticsRunOptions:
    """Validated operator-selected options for a diagnostics run."""

    selected_checks: list[str]
    targets: list[TcpTarget]
    dns_hosts: list[str]
    profile: DiagnosticProfile | None = None
    enable_ping: bool = False
    enable_trace: bool = False
    capture_raw_commands: bool = False


def build_run_options(
    *,
    checks: str | None = None,
    targets: Iterable[str] | None = None,
    target_file: str | None = None,
    dns_hosts: Iterable[str] | None = None,
    profile_id: str | None = None,
    enable_ping: bool = False,
    enable_trace: bool = False,
    capture_raw_commands: bool = False,
) -> DiagnosticsRunOptions:
    """Build validated run options from operator-facing input values."""

    profile = get_profile(profile_id) if profile_id else None
    default_checks = profile.recommended_checks if profile is not None else DEFAULT_CHECKS
    default_targets = (
        profile.tcp_targets if profile is not None and profile.tcp_targets else DEFAULT_TCP_TARGETS
    )
    default_dns_hosts = (
        profile.dns_hosts if profile is not None and profile.dns_hosts else DEFAULT_DNS_HOSTS
    )

    return DiagnosticsRunOptions(
        selected_checks=parse_check_selection(
            checks,
            allowed_checks=ALLOWED_CHECKS,
            default_checks=default_checks,
        ),
        targets=resolve_tcp_targets(
            list(targets or []),
            target_file,
            default_targets=default_targets,
        ),
        dns_hosts=resolve_dns_hosts(list(dns_hosts or []), default_hosts=default_dns_hosts),
        profile=profile,
        enable_ping=enable_ping,
        enable_trace=enable_trace,
        capture_raw_commands=capture_raw_commands,
    )


def run_diagnostics(
    options: DiagnosticsRunOptions,
    *,
    progress_callback: ProgressCallback | None = None,
) -> EndpointDiagnosticResult:
    """Execute diagnostics for the provided validated options."""

    start = time.perf_counter()
    warnings: list[DiagnosticWarning] = []
    durations_ms: dict[str, int] = {}
    cpu_state, memory_state = _empty_resource_components()
    battery_state: BatteryState | None = None
    disks: list[DiskVolume] = []
    storage_devices: list[StorageDeviceHealth] = []
    network_state = _empty_network_state()
    route_summary = RouteSummary(None, None, False, [])
    dns_state = _empty_dns_state()
    connectivity_state = _empty_connectivity_state()
    service_state = _empty_service_state()
    vpn_state = _empty_vpn_state()
    completed_domains: set[str] = set()
    completed_steps_by_domain: dict[str, int] = {}
    step_breakdown = planned_execution_step_breakdown(options)
    total_steps = planned_execution_step_count(options)
    capture_context = (
        capture_command_output()
        if options.capture_raw_commands
        else nullcontext(cast(list[RawCommandCapture], []))
    )

    LOGGER.info(
        "Running host and network diagnostics for checks: %s",
        ", ".join(options.selected_checks),
    )
    LOGGER.debug(
        (
            "Diagnostics input summary: tcp_targets=%d dns_hosts=%d "
            "enable_ping=%s enable_trace=%s profile=%s raw_capture=%s"
        ),
        len(options.targets),
        len(options.dns_hosts),
        options.enable_ping,
        options.enable_trace,
        options.profile.profile_id if options.profile else None,
        options.capture_raw_commands,
    )

    def emit_progress(*, active_domain: str | None = None) -> None:
        if progress_callback is None or "host" not in completed_domains:
            return
        facts = CollectedFacts(
            host=host,
            resources=ResourceState(
                cpu=cpu_state,
                memory=memory_state,
                disks=disks,
                battery=battery_state,
                storage_devices=storage_devices,
            ),
            network=network_state,
            dns=dns_state,
            connectivity=connectivity_state,
            vpn=vpn_state,
            services=service_state,
        )
        progress_execution = build_execution_records(
            facts,
            options,
            warnings,
            durations_ms,
            completed_domains=completed_domains,
            active_domain=active_domain,
        )
        progress_callback(
            progress_execution,
            active_domain,
            sum(completed_steps_by_domain.values()),
            total_steps,
            dict(completed_steps_by_domain),
        )

    with capture_context as raw_command_capture:
        host_start = time.perf_counter()
        host, host_warnings = collect_host_basics()
        durations_ms["host"] = int((time.perf_counter() - host_start) * 1000)
        warnings.extend(host_warnings)
        completed_domains.add("host")
        completed_steps_by_domain["host"] = step_breakdown["host"]
        emit_progress(
            active_domain=_next_selected_domain(completed_domains, options.selected_checks)
        )

        if "resources" in options.selected_checks:
            resources_start = time.perf_counter()
            cpu_state, memory_state, battery_state, resource_warnings = collect_resource_state(
                progress_callback=lambda completed_steps: _update_domain_steps(
                    completed_steps_by_domain,
                    "resources",
                    completed_steps,
                    emit_progress,
                ),
            )
            durations_ms["resources"] = int((time.perf_counter() - resources_start) * 1000)
            warnings.extend(resource_warnings)
            completed_domains.add("resources")
            completed_steps_by_domain["resources"] = step_breakdown["resources"]
            emit_progress(
                active_domain=_next_selected_domain(completed_domains, options.selected_checks)
            )
        else:
            cpu_state, memory_state = _empty_resource_components()
            battery_state = None

        if "storage" in options.selected_checks:
            storage_start = time.perf_counter()
            disks, storage_devices, storage_warnings = collect_storage_state(
                progress_callback=lambda completed_steps: _update_domain_steps(
                    completed_steps_by_domain,
                    "storage",
                    completed_steps,
                    emit_progress,
                ),
            )
            durations_ms["storage"] = int((time.perf_counter() - storage_start) * 1000)
            completed_domains.add("storage")
            completed_steps_by_domain["storage"] = step_breakdown["storage"]
            emit_progress(
                active_domain=_next_selected_domain(completed_domains, options.selected_checks)
            )
        else:
            disks, storage_devices, storage_warnings = [], [], []
        warnings.extend(storage_warnings)

        if "network" in options.selected_checks:
            network_start = time.perf_counter()
            network_state, network_warnings = collect_network_state(
                progress_callback=lambda completed_steps: _update_domain_steps(
                    completed_steps_by_domain,
                    "network",
                    completed_steps,
                    emit_progress,
                ),
            )
            durations_ms["network"] = int((time.perf_counter() - network_start) * 1000)
            completed_domains.add("network")
            completed_steps_by_domain["network"] = step_breakdown["network"]
            emit_progress(
                active_domain=_next_selected_domain(completed_domains, options.selected_checks)
            )
        else:
            network_state, network_warnings = _empty_network_state(), []
        warnings.extend(network_warnings)

        if "routing" in options.selected_checks:
            routing_start = time.perf_counter()
            route_summary, route_warnings = collect_route_summary()
            durations_ms["routing"] = int((time.perf_counter() - routing_start) * 1000)
            completed_domains.add("routing")
            completed_steps_by_domain["routing"] = step_breakdown["routing"]
            emit_progress(
                active_domain=_next_selected_domain(completed_domains, options.selected_checks)
            )
        else:
            route_summary, route_warnings = RouteSummary(None, None, False, []), []
        warnings.extend(route_warnings)
        network_state.route_summary = route_summary

        if "dns" in options.selected_checks:
            dns_start = time.perf_counter()
            dns_state, dns_warnings = collect_dns_state(
                options.dns_hosts,
                progress_callback=lambda completed_steps: _update_domain_steps(
                    completed_steps_by_domain,
                    "dns",
                    completed_steps,
                    emit_progress,
                ),
            )
            durations_ms["dns"] = int((time.perf_counter() - dns_start) * 1000)
            completed_domains.add("dns")
            completed_steps_by_domain["dns"] = step_breakdown["dns"]
            emit_progress(
                active_domain=_next_selected_domain(completed_domains, options.selected_checks)
            )
        else:
            dns_state, dns_warnings = _empty_dns_state(), []
        warnings.extend(dns_warnings)

        if "connectivity" in options.selected_checks:
            connectivity_start = time.perf_counter()
            connectivity_state, connectivity_warnings = collect_connectivity_state(
                targets=options.targets,
                enable_ping=options.enable_ping,
                enable_trace=options.enable_trace,
                progress_callback=lambda completed_steps: _update_domain_steps(
                    completed_steps_by_domain,
                    "connectivity",
                    completed_steps,
                    emit_progress,
                ),
            )
            durations_ms["connectivity"] = int((time.perf_counter() - connectivity_start) * 1000)
            completed_domains.add("connectivity")
            completed_steps_by_domain["connectivity"] = step_breakdown["connectivity"]
            emit_progress(
                active_domain=_next_selected_domain(completed_domains, options.selected_checks)
            )
        else:
            connectivity_state, connectivity_warnings = _empty_connectivity_state(), []
        warnings.extend(connectivity_warnings)

        if "services" in options.selected_checks:
            services_start = time.perf_counter()
            service_state = collect_service_state(
                options.targets,
                progress_callback=lambda completed_steps: _update_domain_steps(
                    completed_steps_by_domain,
                    "services",
                    completed_steps,
                    emit_progress,
                ),
            )
            durations_ms["services"] = int((time.perf_counter() - services_start) * 1000)
            completed_domains.add("services")
            completed_steps_by_domain["services"] = step_breakdown["services"]
            emit_progress(
                active_domain=_next_selected_domain(completed_domains, options.selected_checks)
            )
        else:
            service_state = _empty_service_state()

        if "vpn" in options.selected_checks:
            vpn_start = time.perf_counter()
            vpn_state = collect_vpn_state(network_state, route_summary)
            durations_ms["vpn"] = int((time.perf_counter() - vpn_start) * 1000)
            completed_domains.add("vpn")
            completed_steps_by_domain["vpn"] = step_breakdown["vpn"]
            emit_progress(active_domain=None)
        else:
            vpn_state = _empty_vpn_state()

    resources = ResourceState(
        cpu=cpu_state,
        memory=memory_state,
        disks=disks,
        battery=battery_state,
        storage_devices=storage_devices,
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
    findings = enrich_findings(findings)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    execution = build_execution_records(facts, options, warnings, durations_ms)
    guided_experience = build_guided_experience(findings, execution, options.profile)

    return EndpointDiagnosticResult(
        metadata=Metadata(
            project_name="occams-beard",
            version=__version__,
            generated_at=utc_now_iso(),
            elapsed_ms=elapsed_ms,
            selected_checks=options.selected_checks,
            profile_id=options.profile.profile_id if options.profile else None,
            profile_name=options.profile.name if options.profile else None,
            issue_category=options.profile.issue_category if options.profile else None,
        ),
        platform=PlatformInfo(
            system=python_platform.system(),
            release=python_platform.release(),
            version=python_platform.version(),
            machine=python_platform.machine(),
            python_version=python_platform.python_version(),
        ),
        facts=facts,
        schema_version=RESULT_SCHEMA_VERSION,
        findings=findings,
        probable_fault_domain=cast(FaultDomain, probable_fault_domain),
        warnings=warnings,
        execution=execution,
        guided_experience=guided_experience,
        raw_command_capture=list(raw_command_capture),
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


def _next_selected_domain(
    completed_domains: set[str],
    selected_checks: list[str],
) -> str | None:
    for domain in selected_checks:
        if domain not in completed_domains:
            return domain
    return None


def _update_domain_steps(
    completed_steps_by_domain: dict[str, int],
    domain: str,
    completed_steps: int,
    emit_progress: Callable[..., None],
) -> None:
    completed_steps_by_domain[domain] = completed_steps
    emit_progress(active_domain=domain)
from occams_beard.explanations import build_guided_experience, enrich_findings
