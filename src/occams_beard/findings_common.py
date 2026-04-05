"""Shared helpers for deterministic findings evaluation."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from occams_beard.models import CollectedFacts, ServiceCheck, TcpConnectivityCheck
from occams_beard.utils.validation import is_private_or_loopback_host


def target_is_numeric_ip(check: TcpConnectivityCheck) -> bool:
    try:
        ipaddress.ip_address(check.target.host)
    except ValueError:
        return False
    return True


def network_explanation_not_supported(
    facts: CollectedFacts,
    *,
    enabled_checks: set[str],
) -> bool:
    if "connectivity" not in enabled_checks:
        return False

    public_tcp_checks = [
        check
        for check in facts.connectivity.tcp_checks
        if not is_private_or_loopback_host(check.target.host)
    ]
    if not public_tcp_checks or any(not check.success for check in public_tcp_checks):
        return False
    if "dns" in enabled_checks and facts.dns.checks and any(
        not check.success for check in facts.dns.checks
    ):
        return False
    if "routing" in enabled_checks and not facts.network.route_summary.has_default_route:
        return False
    return facts.connectivity.internet_reachable


def network_health_evidence(
    facts: CollectedFacts,
    *,
    enabled_checks: set[str],
) -> list[str]:
    evidence: list[str] = []
    if "routing" in enabled_checks and facts.network.route_summary.has_default_route:
        default_route_target = (
            facts.network.route_summary.default_gateway
            or facts.network.route_summary.default_interface
            or "a configured interface"
        )
        evidence.append(
            f"Routing summary still shows a default route via {default_route_target}."
        )
    if "dns" in enabled_checks:
        successful_dns = [check for check in facts.dns.checks if check.success]
        if successful_dns:
            evidence.append(f"DNS checks succeeded: {format_dns_hosts(successful_dns)}.")
    if "connectivity" in enabled_checks:
        public_tcp_checks = [
            check
            for check in facts.connectivity.tcp_checks
            if not is_private_or_loopback_host(check.target.host)
        ]
        successful_public_tcp = [check for check in public_tcp_checks if check.success]
        if successful_public_tcp:
            evidence.append(
                f"External TCP checks succeeded: {format_tcp_targets(successful_public_tcp)}."
            )
        if facts.connectivity.internet_reachable:
            evidence.append("Generic internet reachability checks succeeded.")
    return evidence


def format_ratio(numerator: int | None, denominator: int | None) -> str:
    if numerator is None or denominator is None or denominator == 0:
        return "an unknown ratio"
    return f"{(numerator / denominator):.1%}"


def format_utc_offset(offset_minutes: int | None) -> str:
    if offset_minutes is None:
        return "unknown"
    sign = "+" if offset_minutes >= 0 else "-"
    total_minutes = abs(offset_minutes)
    hours, minutes = divmod(total_minutes, 60)
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def format_dns_hosts(checks: Iterable[object]) -> str:
    items: list[str] = []
    for check in checks:
        hostname = getattr(check, "hostname", None)
        if not isinstance(hostname, str):
            continue
        error = getattr(check, "error", None)
        if isinstance(error, str) and error:
            items.append(f"{hostname} ({error})")
            continue
        resolved_addresses = getattr(check, "resolved_addresses", None)
        if isinstance(resolved_addresses, list) and resolved_addresses:
            items.append(f"{hostname} -> {', '.join(resolved_addresses[:2])}")
            continue
        items.append(hostname)
    return ", ".join(items[:3]) + (" and more" if len(items) > 3 else "")


def format_tcp_targets(checks: Iterable[TcpConnectivityCheck]) -> str:
    items = []
    for check in checks:
        status = "ok" if check.success else (check.error or "failed")
        items.append(f"{check.target.host}:{check.target.port} ({status})")
    return ", ".join(items[:3]) + (" and more" if len(items) > 3 else "")


def format_service_targets(checks: Iterable[ServiceCheck]) -> str:
    items = []
    for check in checks:
        label = check.target.label or f"{check.target.host}:{check.target.port}"
        status = "ok" if check.success else (check.error or "failed")
        items.append(f"{label} ({status})")
    return ", ".join(items[:3]) + (" and more" if len(items) > 3 else "")


def format_process_category(value: str) -> str:
    return {
        "browser": "browser",
        "collaboration": "collaboration apps",
        "container_runtime": "container runtime",
        "database": "database",
        "ide": "IDE or editor",
        "other": "other processes",
        "vm": "VM",
    }.get(value, value.replace("_", " "))


def format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    suffixes = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    for suffix in suffixes:
        if size < 1024 or suffix == suffixes[-1]:
            return f"{size:.1f} {suffix}"
        size /= 1024
    return f"{value} B"
