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
from endpoint_diagnostics_lab.defaults import (
    ALLOWED_CHECKS,
    DEFAULT_CHECKS,
    DEFAULT_DNS_HOSTS,
    DEFAULT_TCP_TARGETS,
)
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
from endpoint_diagnostics_lab.utils.validation import (
    parse_check_selection,
    resolve_dns_hosts,
    resolve_tcp_targets,
)


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        prog="endpoint-diagnostics-lab",
        usage="endpoint-diagnostics-lab run [options]",
        description="Single operator-facing command for endpoint diagnostics.",
        epilog="Use 'endpoint-diagnostics-lab run --help' for the full run workflow and options.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    run_parser = subparsers.add_parser(
        "run",
        help="Run the default diagnostic suite.",
        description=(
            "Run endpoint diagnostics.\n"
            "With no flags, the default suite runs against built-in DNS and TCP targets "
            "and prints a human-readable report."
        ),
        epilog=_run_examples_text(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_parser.set_defaults(handler=_run_command)

    scope_group = run_parser.add_argument_group("Scope")
    scope_group.add_argument(
        "--checks",
        metavar="LIST",
        help=(
            "Comma-separated diagnostic domains. "
            f"Supported values: {', '.join(ALLOWED_CHECKS)}."
        ),
    )

    target_group = run_parser.add_argument_group("Targets")
    target_group.add_argument(
        "--target",
        metavar="HOST:PORT",
        action="append",
        default=[],
        help="Repeat to add TCP targets as host:port.",
    )
    target_group.add_argument(
        "--target-file",
        metavar="PATH",
        help="Load TCP targets from a JSON array of host:port strings or {host, port, label} objects.",
    )
    target_group.add_argument(
        "--dns-host",
        metavar="HOST",
        action="append",
        default=[],
        help="Repeat to add DNS resolution hostnames.",
    )

    output_group = run_parser.add_argument_group("Output")
    output_group.add_argument(
        "--json-out",
        metavar="PATH",
        help="Write structured JSON output to PATH.",
    )
    output_group.add_argument(
        "--suppress-report",
        action="store_true",
        help="Skip the human-readable terminal report.",
    )

    probe_group = run_parser.add_argument_group("Optional probes")
    probe_group.add_argument(
        "--enable-ping",
        action="store_true",
        help="Enable best-effort ping checks.",
    )
    probe_group.add_argument(
        "--enable-trace",
        action="store_true",
        help="Enable best-effort traceroute or tracert checks.",
    )

    logging_group = run_parser.add_argument_group("Logging")
    logging_group.add_argument("--verbose", action="store_true", help="Enable INFO-level logging.")
    logging_group.add_argument("--debug", action="store_true", help="Enable DEBUG-level logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        return 2

    _configure_logging(verbose=args.verbose, debug=args.debug)

    try:
        return handler(args)
    except ValueError as exc:
        parser.error(str(exc))
    except Exception as exc:  # pragma: no cover - exercised through exit path tests.
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            LOGGER.exception("Diagnostics execution failed.")
        else:
            LOGGER.error("Diagnostics execution failed: %s", exc)
        return 1


def _run_command(args: argparse.Namespace) -> int:
    start = time.perf_counter()
    selected_checks = parse_check_selection(
        args.checks,
        allowed_checks=ALLOWED_CHECKS,
        default_checks=DEFAULT_CHECKS,
    )
    warnings = []

    targets = resolve_tcp_targets(
        args.target,
        args.target_file,
        default_targets=DEFAULT_TCP_TARGETS,
    )
    dns_hosts = resolve_dns_hosts(args.dns_host, default_hosts=DEFAULT_DNS_HOSTS)

    LOGGER.info("Running endpoint diagnostics for checks: %s", ", ".join(selected_checks))
    LOGGER.debug(
        "Diagnostics input summary: tcp_targets=%d dns_hosts=%d json_out=%s suppress_report=%s "
        "enable_ping=%s enable_trace=%s",
        len(targets),
        len(dns_hosts),
        bool(args.json_out),
        args.suppress_report,
        args.enable_ping,
        args.enable_trace,
    )

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


def _run_examples_text() -> str:
    """Return operator-oriented example commands for run help output."""

    return (
        "Examples:\n"
        "  endpoint-diagnostics-lab run\n"
        "  endpoint-diagnostics-lab run --json-out report.json\n"
        "  endpoint-diagnostics-lab run --checks network,dns,connectivity\n"
        "  endpoint-diagnostics-lab run --target github.com:443 --target 1.1.1.1:53\n"
        "  endpoint-diagnostics-lab run --target-file sample_output/example-targets.json\n"
        "  endpoint-diagnostics-lab run --enable-ping --enable-trace --verbose\n"
        "  endpoint-diagnostics-lab run --suppress-report --json-out report.json"
    )


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
