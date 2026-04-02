"""CLI orchestration for Endpoint Diagnostics Lab."""

from __future__ import annotations

import argparse
import logging
import platform as python_platform
import sys
import time

from endpoint_diagnostics_lab import __version__
from endpoint_diagnostics_lab.collectors.connectivity import collect_connectivity_state
from endpoint_diagnostics_lab.collectors.dns import collect_dns_state
from endpoint_diagnostics_lab.collectors.network import collect_network_state
from endpoint_diagnostics_lab.collectors.routing import collect_route_summary
from endpoint_diagnostics_lab.collectors.services import collect_service_state
from endpoint_diagnostics_lab.collectors.storage import collect_storage_state
from endpoint_diagnostics_lab.collectors.system import collect_host_basics, collect_resource_state
from endpoint_diagnostics_lab.collectors.vpn import collect_vpn_state
from endpoint_diagnostics_lab.findings import evaluate_selected_findings
from endpoint_diagnostics_lab.models import (
    CollectedFacts,
    CpuState,
    EndpointDiagnosticResult,
    MemoryState,
    Metadata,
    PlatformInfo,
    ResourceState,
    RouteSummary,
)
from endpoint_diagnostics_lab.report import render_report
from endpoint_diagnostics_lab.serializers import write_json_file
from endpoint_diagnostics_lab.utils.time import utc_now_iso
from endpoint_diagnostics_lab.utils.validation import load_targets_file, parse_host_port_target


DEFAULT_CHECKS = ["host", "resources", "storage", "network", "routing", "dns", "connectivity", "vpn", "services"]
DEFAULT_DNS_HOSTS = ["github.com", "python.org"]
ALLOWED_CHECKS = set(DEFAULT_CHECKS)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(prog="endpoint-diagnostics-lab")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run diagnostics")
    run_parser.add_argument("--json-out", help="Write machine-readable output to a JSON file.")
    run_parser.add_argument(
        "--suppress-report",
        action="store_true",
        help="Do not print the human-readable report to stdout.",
    )
    run_parser.add_argument(
        "--checks",
        help="Comma-separated diagnostic domains to run.",
    )
    run_parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Repeatable host:port TCP or service target.",
    )
    run_parser.add_argument(
        "--target-file",
        help="JSON file containing a list of host:port strings or {host, port, label} objects.",
    )
    run_parser.add_argument(
        "--dns-host",
        action="append",
        default=[],
        help="Repeatable hostname for DNS resolution checks.",
    )
    run_parser.add_argument(
        "--enable-ping",
        action="store_true",
        help="Enable best-effort ping checks.",
    )
    run_parser.add_argument(
        "--enable-trace",
        action="store_true",
        help="Enable best-effort traceroute or tracert checks.",
    )
    run_parser.add_argument("--verbose", action="store_true", help="Enable verbose logging.")
    run_parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args(argv)

    _configure_logging(verbose=args.verbose, debug=args.debug)

    if args.command == "run":
        try:
            return _run_command(args)
        except ValueError as exc:
            parser.error(str(exc))
    parser.error(f"Unsupported command: {args.command}")
    return 2


def _run_command(args: argparse.Namespace) -> int:
    start = time.perf_counter()
    selected_checks = _parse_checks(args.checks)
    warnings = []

    targets = _load_targets(args.target, args.target_file)
    dns_hosts = args.dns_host or list(DEFAULT_DNS_HOSTS)

    host, host_warnings = collect_host_basics()
    warnings.extend(host_warnings)

    if "resources" in selected_checks:
        cpu_state, memory_state, resource_warnings = collect_resource_state()
        warnings.extend(resource_warnings)
    else:
        cpu_state, memory_state = _empty_resource_components()

    disks, storage_warnings = collect_storage_state() if "storage" in selected_checks else ([], [])
    warnings.extend(storage_warnings)

    resources = ResourceState(cpu=cpu_state, memory=memory_state, disks=disks)

    network_state, network_warnings = collect_network_state() if "network" in selected_checks else (_empty_network_state(), [])
    warnings.extend(network_warnings)

    route_summary, route_warnings = collect_route_summary() if "routing" in selected_checks else (RouteSummary(None, None, False, []), [])
    warnings.extend(route_warnings)
    network_state.route_summary = route_summary

    dns_state, dns_warnings = collect_dns_state(dns_hosts) if "dns" in selected_checks else (_empty_dns_state(), [])
    warnings.extend(dns_warnings)

    connectivity_state, connectivity_warnings = (
        collect_connectivity_state(
            targets=targets,
            enable_ping=args.enable_ping,
            enable_trace=args.enable_trace,
        )
        if "connectivity" in selected_checks
        else (_empty_connectivity_state(), [])
    )
    warnings.extend(connectivity_warnings)

    service_state = collect_service_state(targets) if "services" in selected_checks else _empty_service_state()
    vpn_state = collect_vpn_state(network_state, route_summary) if "vpn" in selected_checks else _empty_vpn_state()

    facts = CollectedFacts(
        host=host,
        resources=resources,
        network=network_state,
        dns=dns_state,
        connectivity=connectivity_state,
        vpn=vpn_state,
        services=service_state,
    )
    findings, probable_fault_domain = evaluate_selected_findings(facts, selected_checks)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    result = EndpointDiagnosticResult(
        metadata=Metadata(
            project_name="endpoint-diagnostics-lab",
            version=__version__,
            generated_at=utc_now_iso(),
            elapsed_ms=elapsed_ms,
            selected_checks=selected_checks,
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

    json_path = None
    if args.json_out:
        json_path = str(write_json_file(result, args.json_out))

    if not args.suppress_report:
        print(render_report(result, json_path=json_path))

    return 0


def _parse_checks(raw_value: str | None) -> list[str]:
    if not raw_value:
        return list(DEFAULT_CHECKS)
    checks = [item.strip() for item in raw_value.split(",") if item.strip()]
    if not checks:
        return list(DEFAULT_CHECKS)

    invalid = [check for check in checks if check not in ALLOWED_CHECKS]
    if invalid:
        raise ValueError(
            "Unsupported diagnostic domains requested: "
            + ", ".join(sorted(set(invalid)))
        )
    return checks


def _configure_logging(verbose: bool, debug: bool) -> None:
    level = logging.WARNING
    if verbose:
        level = logging.INFO
    if debug:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )


def _load_targets(raw_targets: list[str], target_file: str | None):
    targets = [parse_host_port_target(item) for item in raw_targets]
    if target_file:
        targets.extend(load_targets_file(target_file))
    return targets


def _empty_network_state():
    from endpoint_diagnostics_lab.models import NetworkState

    return NetworkState()


def _empty_dns_state():
    from endpoint_diagnostics_lab.models import DnsState

    return DnsState()


def _empty_connectivity_state():
    from endpoint_diagnostics_lab.models import ConnectivityState

    return ConnectivityState(internet_reachable=False)


def _empty_service_state():
    from endpoint_diagnostics_lab.models import ServiceState

    return ServiceState()


def _empty_vpn_state():
    from endpoint_diagnostics_lab.models import VpnState

    return VpnState()


def _empty_resource_components() -> tuple[CpuState, MemoryState]:
    return CpuState(logical_cpus=None), MemoryState(
        total_bytes=None,
        available_bytes=None,
        free_bytes=None,
        pressure_level=None,
    )
