"""Mutable orchestration state for a single diagnostics run."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from occams_beard.execution import build_execution_records
from occams_beard.models import (
    BatteryState,
    CollectedFacts,
    ConnectivityState,
    CpuState,
    DiagnosticWarning,
    DiskVolume,
    DnsState,
    DomainExecution,
    HostBasics,
    MemoryState,
    NetworkState,
    ResourceState,
    RouteSummary,
    ServiceState,
    StorageDeviceHealth,
    VpnState,
)

if TYPE_CHECKING:
    from occams_beard.domain_registry import PlannedDiagnosticDomain
    from occams_beard.run_options import DiagnosticsRunOptions


ProgressCallback = Callable[[list[DomainExecution], str | None, int, int, dict[str, int]], None]


@dataclass(slots=True)
class DiagnosticsRunContext:
    """Track mutable state, timing, and progress for a diagnostics run."""

    options: DiagnosticsRunOptions
    execution_plan: tuple[PlannedDiagnosticDomain, ...]
    progress_callback: ProgressCallback | None = None
    warnings: list[DiagnosticWarning] = field(default_factory=list)
    durations_ms: dict[str, int] = field(default_factory=dict)
    completed_domains: set[str] = field(default_factory=set)
    completed_steps_by_domain: dict[str, int] = field(default_factory=dict)
    host: HostBasics | None = None
    resources: ResourceState = field(default_factory=lambda: ResourceState(*_empty_resource_parts()))
    network: NetworkState = field(default_factory=NetworkState)
    dns: DnsState = field(default_factory=DnsState)
    connectivity: ConnectivityState = field(
        default_factory=lambda: ConnectivityState(internet_reachable=False)
    )
    vpn: VpnState = field(default_factory=VpnState)
    services: ServiceState = field(default_factory=ServiceState)
    total_steps: int = field(init=False, default=0)
    _selected_execution_order: tuple[str, ...] = field(init=False, default=(), repr=False)
    _planned_steps_by_domain: dict[str, int] = field(init=False, default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._selected_execution_order = tuple(planned.domain for planned in self.execution_plan)
        self._planned_steps_by_domain = {
            planned.domain: planned.step_count for planned in self.execution_plan
        }
        self.total_steps = sum(self._planned_steps_by_domain.values())

    def set_host(self, host: HostBasics) -> None:
        self.host = host

    def set_resources(
        self,
        *,
        cpu: CpuState,
        memory: MemoryState,
        battery: BatteryState | None,
    ) -> None:
        self.resources.cpu = cpu
        self.resources.memory = memory
        self.resources.battery = battery

    def set_storage(
        self,
        *,
        disks: list[DiskVolume],
        storage_devices: list[StorageDeviceHealth],
    ) -> None:
        self.resources.disks = disks
        self.resources.storage_devices = storage_devices

    def set_network(self, network: NetworkState) -> None:
        self.network = network

    def set_route_summary(self, route_summary: RouteSummary) -> None:
        self.network.route_summary = route_summary

    def set_dns(self, dns: DnsState) -> None:
        self.dns = dns

    def set_connectivity(self, connectivity: ConnectivityState) -> None:
        self.connectivity = connectivity

    def set_services(self, services: ServiceState) -> None:
        self.services = services

    def set_vpn(self, vpn: VpnState) -> None:
        self.vpn = vpn

    def record_domain_progress(self, domain: str, completed_steps: int) -> None:
        self.completed_steps_by_domain[domain] = completed_steps
        self.emit_progress(active_domain=domain)

    def complete_domain(
        self,
        domain: str,
        *,
        started_at: float,
        warnings: Iterable[DiagnosticWarning] = (),
    ) -> None:
        self.durations_ms[domain] = int((time.perf_counter() - started_at) * 1000)
        self.warnings.extend(warnings)
        self.completed_domains.add(domain)
        self.completed_steps_by_domain[domain] = self._planned_steps_by_domain.get(domain, 0)
        self.emit_progress(active_domain=self.next_selected_domain())

    def next_selected_domain(self) -> str | None:
        for domain in self._selected_execution_order:
            if domain not in self.completed_domains:
                return domain
        return None

    def current_facts(self) -> CollectedFacts:
        if self.host is None:
            raise RuntimeError("Host facts are not available until the host domain completes.")
        return CollectedFacts(
            host=self.host,
            resources=self.resources,
            network=self.network,
            dns=self.dns,
            connectivity=self.connectivity,
            vpn=self.vpn,
            services=self.services,
        )

    def emit_progress(self, *, active_domain: str | None) -> None:
        if (
            self.progress_callback is None
            or self.host is None
            or "host" not in self.completed_domains
        ):
            return
        self.progress_callback(
            build_execution_records(
                self.current_facts(),
                self.options,
                self.warnings,
                self.durations_ms,
                completed_domains=self.completed_domains,
                active_domain=active_domain,
            ),
            active_domain,
            sum(self.completed_steps_by_domain.values()),
            self.total_steps,
            dict(self.completed_steps_by_domain),
        )


def _empty_resource_parts() -> tuple[CpuState, MemoryState]:
    return CpuState(logical_cpus=None), MemoryState(
        total_bytes=None,
        available_bytes=None,
        free_bytes=None,
        pressure_level=None,
    )
