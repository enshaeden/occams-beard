"""Collectors for DNS resolution checks."""

from __future__ import annotations

from collections.abc import Callable

from occams_beard.models import DiagnosticWarning, DnsResolutionCheck, DnsState
from occams_beard.platform import current_platform, linux, macos, windows
from occams_beard.utils.resolution import (
    HOSTNAME_RESOLUTION_TIMEOUT_SECONDS,
    resolve_hostname_addresses,
)


def collect_dns_state(
    hostnames: list[str],
    *,
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[DnsState, list[DiagnosticWarning]]:
    """Collect resolver configuration and resolution results."""

    warnings: list[DiagnosticWarning] = []
    resolvers = _read_resolvers()
    checks: list[DnsResolutionCheck] = []
    completed_steps = 1

    if progress_callback is not None:
        progress_callback(completed_steps)

    for hostname in hostnames:
        resolution = resolve_hostname_addresses(hostname)
        if resolution.timed_out:
            warnings.append(
                DiagnosticWarning(
                    domain="dns",
                    code="hostname-resolution-timeout",
                    message=(
                        "Hostname resolution timed out after "
                        f"{HOSTNAME_RESOLUTION_TIMEOUT_SECONDS:.1f}s for {hostname}."
                    ),
                )
            )
            checks.append(
                DnsResolutionCheck(
                    hostname=hostname,
                    success=False,
                    error="hostname-resolution-timeout",
                    duration_ms=resolution.duration_ms,
                )
            )
            completed_steps += 1
            if progress_callback is not None:
                progress_callback(completed_steps)
            continue

        if resolution.error is not None:
            checks.append(
                DnsResolutionCheck(
                    hostname=hostname,
                    success=False,
                    error=resolution.error,
                    duration_ms=resolution.duration_ms,
                )
            )
            completed_steps += 1
            if progress_callback is not None:
                progress_callback(completed_steps)
            continue

        addresses = resolution.addresses
        checks.append(
            DnsResolutionCheck(
                hostname=hostname,
                success=bool(addresses),
                resolved_addresses=addresses,
                error=None if addresses else "no-addresses-returned",
                duration_ms=resolution.duration_ms,
            )
        )
        completed_steps += 1
        if progress_callback is not None:
            progress_callback(completed_steps)

    if not resolvers:
        warnings.append(
            DiagnosticWarning(
                domain="dns",
                code="resolver-unavailable",
                message="Configured resolvers could not be determined on this endpoint.",
            )
        )

    return DnsState(resolvers=resolvers, checks=checks), warnings


def _read_resolvers() -> list[str]:
    platform_name = current_platform()
    if platform_name == "linux":
        return linux.read_resolvers()
    if platform_name == "macos":
        return macos.read_resolvers()
    if platform_name == "windows":
        return windows.read_resolvers()
    return []
