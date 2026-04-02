"""Collectors for DNS resolution checks."""

from __future__ import annotations

import socket

from endpoint_diagnostics_lab.models import DiagnosticWarning, DnsResolutionCheck, DnsState
from endpoint_diagnostics_lab.platform import current_platform
from endpoint_diagnostics_lab.platform import linux, macos, windows
from endpoint_diagnostics_lab.utils.validation import dedupe_preserve_order


def collect_dns_state(hostnames: list[str]) -> tuple[DnsState, list[DiagnosticWarning]]:
    """Collect resolver configuration and resolution results."""

    warnings: list[DiagnosticWarning] = []
    resolvers = _read_resolvers()
    checks: list[DnsResolutionCheck] = []

    for hostname in hostnames:
        try:
            results = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            checks.append(
                DnsResolutionCheck(
                    hostname=hostname,
                    success=False,
                    error=str(exc),
                )
            )
            continue

        addresses = dedupe_preserve_order(item[4][0] for item in results if item[4])
        checks.append(
            DnsResolutionCheck(
                hostname=hostname,
                success=bool(addresses),
                resolved_addresses=addresses,
                error=None if addresses else "no-addresses-returned",
            )
        )

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
