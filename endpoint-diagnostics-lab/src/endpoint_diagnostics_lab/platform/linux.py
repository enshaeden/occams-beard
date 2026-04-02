"""Linux-specific collection helpers."""

from __future__ import annotations

from pathlib import Path

from endpoint_diagnostics_lab.utils.parsing import (
    parse_ip_addr_show,
    parse_linux_ip_route,
    parse_netstat_rn,
    parse_resolv_conf,
)
from endpoint_diagnostics_lab.utils.subprocess import CommandResult, run_command


def read_uptime_seconds() -> int | None:
    """Read system uptime from `/proc/uptime`."""

    path = Path("/proc/uptime")
    if not path.exists():
        return None
    raw_value = path.read_text(encoding="utf-8").strip().split()[0]
    return int(float(raw_value))


def read_memory_snapshot() -> dict[str, int | None]:
    """Read memory data from `/proc/meminfo`."""

    path = Path("/proc/meminfo")
    if not path.exists():
        return {"total_bytes": None, "available_bytes": None, "free_bytes": None}

    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        number = value.strip().split()[0]
        if number.isdigit():
            values[key] = int(number) * 1024

    return {
        "total_bytes": values.get("MemTotal"),
        "available_bytes": values.get("MemAvailable", values.get("MemFree")),
        "free_bytes": values.get("MemFree"),
    }


def read_interfaces() -> tuple[list[dict[str, object]], CommandResult]:
    """Collect interface inventory."""

    result = run_command(["ip", "addr", "show"])
    if result.succeeded:
        return parse_ip_addr_show(result.stdout), result

    fallback = run_command(["ifconfig"])
    if fallback.succeeded:
        from endpoint_diagnostics_lab.utils.parsing import parse_ifconfig

        return parse_ifconfig(fallback.stdout), fallback
    return [], fallback


def read_routes() -> tuple[dict[str, object], CommandResult]:
    """Collect route inventory."""

    result = run_command(["ip", "route", "show"])
    if result.succeeded:
        return parse_linux_ip_route(result.stdout), result

    fallback = run_command(["netstat", "-rn"])
    if fallback.succeeded:
        return parse_netstat_rn(fallback.stdout), fallback
    return {
        "default_gateway": None,
        "default_interface": None,
        "has_default_route": False,
        "routes": [],
    }, fallback


def read_resolvers() -> list[str]:
    """Read resolvers from `/etc/resolv.conf`."""

    path = Path("/etc/resolv.conf")
    if not path.exists():
        return []
    return parse_resolv_conf(path.read_text(encoding="utf-8"))
