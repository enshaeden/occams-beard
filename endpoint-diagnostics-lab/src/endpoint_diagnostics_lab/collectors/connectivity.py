"""Collectors for TCP, ping, and traceroute checks."""

from __future__ import annotations

import logging
import socket
import time

from endpoint_diagnostics_lab.models import (
    ConnectivityState,
    DiagnosticWarning,
    PingResult,
    TcpConnectivityCheck,
    TcpTarget,
    TraceHop,
    TraceResult,
)
from endpoint_diagnostics_lab.platform import current_platform
from endpoint_diagnostics_lab.utils.parsing import parse_ping_output, parse_traceroute_output
from endpoint_diagnostics_lab.utils.subprocess import run_command


LOGGER = logging.getLogger(__name__)

DEFAULT_TCP_TARGETS = [
    TcpTarget(host="github.com", port=443, label="github-https"),
    TcpTarget(host="1.1.1.1", port=53, label="cloudflare-dns"),
]


def collect_connectivity_state(
    targets: list[TcpTarget],
    enable_ping: bool = False,
    enable_trace: bool = False,
) -> tuple[ConnectivityState, list[DiagnosticWarning]]:
    """Collect connectivity state for the provided targets."""

    warnings: list[DiagnosticWarning] = []
    effective_targets = targets or DEFAULT_TCP_TARGETS
    tcp_checks = [check_tcp_target(target) for target in effective_targets]
    ping_checks: list[PingResult] = []
    trace_results: list[TraceResult] = []

    if enable_ping:
        for target in effective_targets:
            ping_result, ping_warning = check_ping_target(target.host)
            ping_checks.append(ping_result)
            if ping_warning:
                warnings.append(ping_warning)

    if enable_trace:
        for target in effective_targets:
            trace_result, trace_warning = check_trace_target(target.host)
            trace_results.append(trace_result)
            if trace_warning:
                warnings.append(trace_warning)

    internet_reachable = any(check.success for check in tcp_checks)
    return (
        ConnectivityState(
            internet_reachable=internet_reachable,
            tcp_checks=tcp_checks,
            ping_checks=ping_checks,
            trace_results=trace_results,
        ),
        warnings,
    )


def check_tcp_target(target: TcpTarget, timeout: float = 3.0) -> TcpConnectivityCheck:
    """Run a TCP connect test against a host and port."""

    start = time.perf_counter()
    try:
        connection = socket.create_connection((target.host, target.port), timeout=timeout)
    except OSError as exc:
        return TcpConnectivityCheck(
            target=target,
            success=False,
            error=str(exc),
        )

    with connection:
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        ip_used = None
        try:
            peer = connection.getpeername()
            if peer:
                ip_used = str(peer[0])
        except OSError:
            ip_used = None
        return TcpConnectivityCheck(
            target=target,
            success=True,
            latency_ms=latency_ms,
            ip_used=ip_used,
        )


def check_ping_target(host: str) -> tuple[PingResult, DiagnosticWarning | None]:
    """Run a best-effort ping check."""

    platform_name = current_platform()
    if platform_name == "windows":
        args = ["ping", "-n", "1", "-w", "1000", host]
    else:
        args = ["ping", "-c", "1", "-W", "1", host]

    result = run_command(args, timeout=3.0)
    if result.error and result.error.startswith("command-not-found"):
        return (
            PingResult(target=host, success=False, error="ping-command-unavailable"),
            DiagnosticWarning(
                domain="connectivity",
                code="ping-unavailable",
                message="Ping command is unavailable on this endpoint.",
            ),
        )

    parsed = parse_ping_output(result.stdout)
    ping_result = PingResult(
        target=host,
        success=result.succeeded,
        packet_loss_percent=parsed["packet_loss_percent"],
        average_latency_ms=parsed["average_latency_ms"],
        error=None if result.succeeded else result.error or result.stderr.strip() or "ping-failed",
    )
    return ping_result, None


def check_trace_target(host: str) -> tuple[TraceResult, DiagnosticWarning | None]:
    """Run a best-effort traceroute or tracert check."""

    platform_name = current_platform()
    if platform_name == "windows":
        args = ["tracert", "-d", "-h", "5", host]
    else:
        args = ["traceroute", "-m", "5", "-w", "1", host]

    result = run_command(args, timeout=10.0)
    if result.error and result.error.startswith("command-not-found"):
        return (
            TraceResult(
                target=host,
                ran=False,
                success=False,
                error="trace-command-unavailable",
            ),
            DiagnosticWarning(
                domain="connectivity",
                code="trace-unavailable",
                message="Traceroute command is unavailable on this endpoint.",
            ),
        )

    hops = [TraceHop(**hop) for hop in parse_traceroute_output(result.stdout)]
    partial = bool(hops) and any(hop.note == "*" for hop in hops)
    trace_result = TraceResult(
        target=host,
        ran=True,
        success=result.succeeded,
        hops=hops,
        error=None if result.succeeded else result.error or result.stderr.strip() or "trace-failed",
        partial=partial,
    )
    return trace_result, None
