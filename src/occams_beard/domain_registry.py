"""Registered diagnostic domains and execution-plan construction."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from occams_beard.collectors.connectivity import collect_connectivity_state
from occams_beard.collectors.dns import collect_dns_state
from occams_beard.collectors.network import collect_network_state
from occams_beard.collectors.routing import collect_route_summary
from occams_beard.collectors.services import collect_service_state
from occams_beard.collectors.storage import collect_storage_state
from occams_beard.collectors.system import collect_host_basics, collect_resource_state
from occams_beard.collectors.time import collect_time_state
from occams_beard.collectors.vpn import collect_vpn_state
from occams_beard.models import TcpTarget

if TYPE_CHECKING:
    from occams_beard.run_context import DiagnosticsRunContext
    from occams_beard.run_options import DiagnosticsRunOptions


DomainExecutor = Callable[..., None]
StepLabelsBuilder = Callable[..., list[str]]


@dataclass(frozen=True, slots=True)
class DiagnosticDomainDefinition:
    """A registered diagnostic domain and its execution contract."""

    domain: str
    label: str
    execute: DomainExecutor
    planned_step_labels: StepLabelsBuilder
    always_selected: bool = False
    creates_network_egress: bool = False


@dataclass(frozen=True, slots=True)
class PlannedDiagnosticDomain:
    """A concrete planned domain instance for one run."""

    definition: DiagnosticDomainDefinition
    step_labels: tuple[str, ...]

    @property
    def domain(self) -> str:
        return self.definition.domain

    @property
    def step_count(self) -> int:
        return len(self.step_labels)


def build_execution_plan(options: DiagnosticsRunOptions) -> tuple[PlannedDiagnosticDomain, ...]:
    """Build the ordered set of domain executions for a run."""

    selected_domains = set(options.selected_checks)
    plan: list[PlannedDiagnosticDomain] = []
    for definition in REGISTERED_DOMAINS:
        if not definition.always_selected and definition.domain not in selected_domains:
            continue
        plan.append(
            PlannedDiagnosticDomain(
                definition=definition,
                step_labels=tuple(definition.planned_step_labels(options)),
            )
        )
    return tuple(plan)


def planned_step_labels_by_domain(options: DiagnosticsRunOptions) -> dict[str, list[str]]:
    """Return step labels for every registered domain."""

    planned_labels: dict[str, list[str]] = {}
    selected_domains = set(options.selected_checks)
    for definition in REGISTERED_DOMAINS:
        if definition.always_selected or definition.domain in selected_domains:
            planned_labels[definition.domain] = list(definition.planned_step_labels(options))
        else:
            planned_labels[definition.domain] = []
    return planned_labels


def iter_registered_domains() -> tuple[DiagnosticDomainDefinition, ...]:
    """Return all registered diagnostic domains in execution order."""

    return REGISTERED_DOMAINS


def _execute_host(options: DiagnosticsRunOptions, context: DiagnosticsRunContext) -> None:
    del options
    started_at = time.perf_counter()
    host, warnings = collect_host_basics()
    context.set_host(host)
    context.complete_domain("host", started_at=started_at, warnings=warnings)


def _execute_resources(options: DiagnosticsRunOptions, context: DiagnosticsRunContext) -> None:
    del options
    started_at = time.perf_counter()
    cpu, memory, battery, process_snapshot, warnings = collect_resource_state(
        progress_callback=lambda completed_steps: context.record_domain_progress(
            "resources",
            completed_steps,
        )
    )
    context.set_resources(
        cpu=cpu,
        memory=memory,
        battery=battery,
        process_snapshot=process_snapshot,
    )
    context.complete_domain("resources", started_at=started_at, warnings=warnings)


def _execute_time(options: DiagnosticsRunOptions, context: DiagnosticsRunContext) -> None:
    started_at = time.perf_counter()
    time_state, warnings = collect_time_state(
        enable_skew_check=options.enable_time_skew_check,
        reference_label=options.time_reference_label,
        reference_url=options.time_reference_url,
        progress_callback=lambda completed_steps: context.record_domain_progress(
            "time",
            completed_steps,
        ),
    )
    context.set_time(time_state)
    context.complete_domain("time", started_at=started_at, warnings=warnings)


def _execute_storage(options: DiagnosticsRunOptions, context: DiagnosticsRunContext) -> None:
    del options
    started_at = time.perf_counter()
    disks, storage_devices, warnings = collect_storage_state(
        progress_callback=lambda completed_steps: context.record_domain_progress(
            "storage",
            completed_steps,
        )
    )
    context.set_storage(disks=disks, storage_devices=storage_devices)
    context.complete_domain("storage", started_at=started_at, warnings=warnings)


def _execute_network(options: DiagnosticsRunOptions, context: DiagnosticsRunContext) -> None:
    del options
    started_at = time.perf_counter()
    network, warnings = collect_network_state(
        progress_callback=lambda completed_steps: context.record_domain_progress(
            "network",
            completed_steps,
        )
    )
    context.set_network(network)
    context.complete_domain("network", started_at=started_at, warnings=warnings)


def _execute_routing(options: DiagnosticsRunOptions, context: DiagnosticsRunContext) -> None:
    del options
    started_at = time.perf_counter()
    route_summary, warnings = collect_route_summary()
    context.set_route_summary(route_summary)
    context.complete_domain("routing", started_at=started_at, warnings=warnings)


def _execute_dns(options: DiagnosticsRunOptions, context: DiagnosticsRunContext) -> None:
    started_at = time.perf_counter()
    dns, warnings = collect_dns_state(
        options.dns_hosts,
        progress_callback=lambda completed_steps: context.record_domain_progress(
            "dns",
            completed_steps,
        ),
    )
    context.set_dns(dns)
    context.complete_domain("dns", started_at=started_at, warnings=warnings)


def _execute_connectivity(options: DiagnosticsRunOptions, context: DiagnosticsRunContext) -> None:
    started_at = time.perf_counter()
    connectivity, warnings = collect_connectivity_state(
        targets=options.targets,
        enable_ping=options.enable_ping,
        enable_trace=options.enable_trace,
        progress_callback=lambda completed_steps: context.record_domain_progress(
            "connectivity",
            completed_steps,
        ),
    )
    context.set_connectivity(connectivity)
    context.complete_domain("connectivity", started_at=started_at, warnings=warnings)


def _execute_services(options: DiagnosticsRunOptions, context: DiagnosticsRunContext) -> None:
    started_at = time.perf_counter()
    services = collect_service_state(
        options.targets,
        progress_callback=lambda completed_steps: context.record_domain_progress(
            "services",
            completed_steps,
        ),
    )
    context.set_services(services)
    context.complete_domain("services", started_at=started_at)


def _execute_vpn(options: DiagnosticsRunOptions, context: DiagnosticsRunContext) -> None:
    del options
    started_at = time.perf_counter()
    vpn = collect_vpn_state(context.network, context.network.route_summary)
    context.set_vpn(vpn)
    context.complete_domain("vpn", started_at=started_at)


def _host_step_labels(options: DiagnosticsRunOptions) -> list[str]:
    del options
    return ["Collecting endpoint identity and uptime"]


def _resource_step_labels(options: DiagnosticsRunOptions) -> list[str]:
    del options
    return [
        "Collecting CPU and load facts",
        "Collecting memory and battery facts",
        "Collecting bounded process-load hints",
    ]


def _time_step_labels(options: DiagnosticsRunOptions) -> list[str]:
    labels = ["Capturing local clock and timezone state"]
    if options.enable_time_skew_check:
        labels.append("Comparing clock with the bounded external reference")
    return labels


def _storage_step_labels(options: DiagnosticsRunOptions) -> list[str]:
    del options
    return [
        "Inspecting mounted volumes",
        "Checking storage device health",
    ]


def _network_step_labels(options: DiagnosticsRunOptions) -> list[str]:
    del options
    return [
        "Collecting interface inventory",
        "Collecting neighbor cache",
    ]


def _routing_step_labels(options: DiagnosticsRunOptions) -> list[str]:
    del options
    return ["Collecting routing inventory"]


def _dns_step_labels(options: DiagnosticsRunOptions) -> list[str]:
    return [
        "Reading resolver configuration",
        *[f"Resolving {hostname}" for hostname in options.dns_hosts],
    ]


def _connectivity_step_labels(options: DiagnosticsRunOptions) -> list[str]:
    labels = [f"Testing TCP reachability to {_target_label(target)}" for target in options.targets]
    if options.enable_ping:
        labels.extend(f"Pinging {target.host}" for target in options.targets)
    if options.enable_trace:
        labels.extend(f"Tracing route to {target.host}" for target in options.targets)
    return labels


def _services_step_labels(options: DiagnosticsRunOptions) -> list[str]:
    return [f"Checking {_target_label(target)}" for target in options.targets]


def _vpn_step_labels(options: DiagnosticsRunOptions) -> list[str]:
    del options
    return ["Checking VPN heuristics"]


def _target_label(target: TcpTarget) -> str:
    if target.label:
        return target.label
    return f"{target.host}:{target.port}"


REGISTERED_DOMAINS: tuple[DiagnosticDomainDefinition, ...] = (
    DiagnosticDomainDefinition(
        domain="host",
        label="Host basics",
        execute=_execute_host,
        planned_step_labels=_host_step_labels,
        always_selected=True,
    ),
    DiagnosticDomainDefinition(
        domain="time",
        label="Clock and time state",
        execute=_execute_time,
        planned_step_labels=_time_step_labels,
    ),
    DiagnosticDomainDefinition(
        domain="resources",
        label="Resource snapshot",
        execute=_execute_resources,
        planned_step_labels=_resource_step_labels,
    ),
    DiagnosticDomainDefinition(
        domain="storage",
        label="Storage snapshot",
        execute=_execute_storage,
        planned_step_labels=_storage_step_labels,
    ),
    DiagnosticDomainDefinition(
        domain="network",
        label="Interface inventory",
        execute=_execute_network,
        planned_step_labels=_network_step_labels,
    ),
    DiagnosticDomainDefinition(
        domain="routing",
        label="Routing inventory",
        execute=_execute_routing,
        planned_step_labels=_routing_step_labels,
    ),
    DiagnosticDomainDefinition(
        domain="dns",
        label="DNS checks",
        execute=_execute_dns,
        planned_step_labels=_dns_step_labels,
        creates_network_egress=True,
    ),
    DiagnosticDomainDefinition(
        domain="connectivity",
        label="Generic connectivity",
        execute=_execute_connectivity,
        planned_step_labels=_connectivity_step_labels,
        creates_network_egress=True,
    ),
    DiagnosticDomainDefinition(
        domain="services",
        label="Configured services",
        execute=_execute_services,
        planned_step_labels=_services_step_labels,
        creates_network_egress=True,
    ),
    DiagnosticDomainDefinition(
        domain="vpn",
        label="VPN heuristics",
        execute=_execute_vpn,
        planned_step_labels=_vpn_step_labels,
    ),
)

NETWORK_EGRESS_DOMAINS = frozenset(
    definition.domain for definition in REGISTERED_DOMAINS if definition.creates_network_egress
)


def domain_creates_network_egress(domain: str, options: DiagnosticsRunOptions) -> bool:
    """Return whether the selected domain will intentionally create network traffic."""

    if domain == "time":
        return domain in options.selected_checks and options.enable_time_skew_check
    return domain in NETWORK_EGRESS_DOMAINS
