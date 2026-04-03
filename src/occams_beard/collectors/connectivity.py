"""Collectors for TCP, ping, and traceroute checks."""

from __future__ import annotations

import logging
import socket
import time
from collections.abc import Callable

from occams_beard.defaults import DEFAULT_TCP_TARGETS
from occams_beard.models import (
    ConnectivityState,
    DiagnosticWarning,
    PingResult,
    TcpConnectivityCheck,
    TcpTarget,
    TraceHop,
    TraceResult,
)
from occams_beard.platform import current_platform
from occams_beard.utils.parsing import parse_ping_output, parse_traceroute_output
from occams_beard.utils.resolution import (
    HOSTNAME_RESOLUTION_TIMEOUT_SECONDS,
    resolve_hostname_addresses,
)
from occams_beard.utils.subprocess import run_command

LOGGER = logging.getLogger(__name__)


def collect_connectivity_state(
    targets: list[TcpTarget],
    enable_ping: bool = False,
    enable_trace: bool = False,
    *,
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[ConnectivityState, list[DiagnosticWarning]]:
    """Collect connectivity state for the provided targets."""

    warnings: list[DiagnosticWarning] = []
    effective_targets = targets or DEFAULT_TCP_TARGETS
    completed_steps = 0
    tcp_checks = []
    for target in effective_targets:
        tcp_checks.append(check_tcp_target(target))
        completed_steps += 1
        if progress_callback is not None:
            progress_callback(completed_steps)
    ping_checks: list[PingResult] = []
    trace_results: list[TraceResult] = []

    if enable_ping:
        for target in effective_targets:
            ping_result, ping_warning = check_ping_target(target.host)
            ping_checks.append(ping_result)
            if ping_warning:
                warnings.append(ping_warning)
            completed_steps += 1
            if progress_callback is not None:
                progress_callback(completed_steps)

    if enable_trace:
        for target in effective_targets:
            trace_result, trace_warnings = check_trace_target(target.host)
            trace_results.append(trace_result)
            warnings.extend(trace_warnings)
            completed_steps += 1
            if progress_callback is not None:
                progress_callback(completed_steps)

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
        duration_ms = int((time.perf_counter() - start) * 1000)
        return TcpConnectivityCheck(
            target=target,
            success=False,
            error=str(exc),
            duration_ms=duration_ms,
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
            duration_ms=int(latency_ms),
        )


def check_ping_target(host: str) -> tuple[PingResult, DiagnosticWarning | None]:
    """Run a best-effort ping check."""

    args = _ping_command_args(host)

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
        duration_ms=result.duration_ms,
    )
    return ping_result, None


def check_trace_target(host: str) -> tuple[TraceResult, list[DiagnosticWarning]]:
    """Run a best-effort traceroute or tracert check."""

    args = _trace_command_args(host)
    target_address, resolution_warnings = _resolve_trace_target(host)

    result = run_command(args, timeout=10.0)
    if result.error and result.error.startswith("command-not-found"):
        return (
            TraceResult(
                target=host,
                ran=False,
                success=False,
                error="trace-command-unavailable",
                target_address=target_address,
                duration_ms=result.duration_ms,
            ),
            [
                *resolution_warnings,
                DiagnosticWarning(
                    domain="connectivity",
                    code="trace-unavailable",
                    message="Traceroute command is unavailable on this endpoint.",
                ),
            ],
        )

    hops = [TraceHop(**hop) for hop in parse_traceroute_output(result.stdout)]
    target_reached = any(_trace_hop_matches_target(hop, host, target_address) for hop in hops)
    last_responding_hop = max(
        (hop.hop for hop in hops if hop.address or hop.host),
        default=None,
    )
    partial = bool(last_responding_hop) and not target_reached
    error = None
    if not target_reached and not partial and not result.succeeded:
        error = result.error or result.stderr.strip() or "trace-failed"
    elif not target_reached and not partial and result.succeeded:
        error = "trace-no-responsive-hops"

    trace_result = TraceResult(
        target=host,
        ran=True,
        success=target_reached,
        hops=hops,
        error=error,
        partial=partial,
        target_address=target_address,
        last_responding_hop=last_responding_hop,
        duration_ms=result.duration_ms,
    )
    return trace_result, resolution_warnings


def _ping_command_args(host: str) -> list[str]:
    """Build platform-appropriate ping arguments."""

    platform_name = current_platform()
    if platform_name == "windows":
        return ["ping", "-n", "10", "-w", "1000", host]
    if platform_name == "macos":
        return ["ping", "-c", "10", "-W", "1000", host]
    return ["ping", "-c", "10", "-W", "1000", host]


def _trace_command_args(host: str) -> list[str]:
    """Build platform-appropriate traceroute arguments."""

    platform_name = current_platform()
    if platform_name == "windows":
        return ["tracert", "-d", "-h", "30", "-w", "1000", host]
    return ["traceroute", "-n", "-m", "30", "-w", "1000", host]


def _resolve_trace_target(host: str) -> tuple[str | None, list[DiagnosticWarning]]:
    if _looks_like_ip_address(host):
        return host, []

    resolution = resolve_hostname_addresses(host)
    if resolution.timed_out:
        return (
            None,
            [
                DiagnosticWarning(
                    domain="connectivity",
                    code="trace-target-resolution-timeout",
                    message=(
                        "Trace target hostname resolution timed out after "
                        f"{HOSTNAME_RESOLUTION_TIMEOUT_SECONDS:.1f}s for {host}."
                    ),
                )
            ],
        )
    if resolution.addresses:
        return resolution.addresses[0], []
    return None, []


def _trace_hop_matches_target(hop: TraceHop, host: str, target_address: str | None) -> bool:
    if hop.address and target_address and hop.address == target_address:
        return True
    if hop.host and target_address and hop.host == target_address:
        return True
    if hop.host and hop.host == host:
        return True
    if hop.address and hop.address == host:
        return True
    return False


def _looks_like_ip_address(value: str) -> bool:
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, value)
        except OSError:
            continue
        return True
    return False
