"""macOS-specific collection helpers."""

from __future__ import annotations

import re
from datetime import datetime

from endpoint_diagnostics_lab.utils.parsing import (
    parse_arp_table,
    parse_ifconfig,
    parse_netstat_rn,
    parse_route_get_default,
)
from endpoint_diagnostics_lab.utils.subprocess import CommandResult, run_command


def read_uptime_seconds() -> int | None:
    """Read system uptime using `sysctl`."""

    result = run_command(["sysctl", "-n", "kern.boottime"])
    if result.succeeded:
        match = re.search(r"sec\s*=\s*(\d+)", result.stdout)
        if match:
            boot_time = int(match.group(1))
            return max(0, int(datetime.now().timestamp()) - boot_time)

    fallback = run_command(["uptime"])
    if not fallback.succeeded:
        return None
    return _parse_uptime_seconds(fallback.stdout)


def read_memory_snapshot() -> dict[str, int | None]:
    """Read memory totals using `sysctl` and `vm_stat`."""

    total_result = run_command(["sysctl", "-n", "hw.memsize"])
    vm_stat_result = run_command(["vm_stat"])
    total_bytes = int(total_result.stdout.strip()) if total_result.succeeded else None
    free_bytes = None
    available_bytes = None

    if vm_stat_result.succeeded:
        page_size_match = re.search(r"page size of (\d+) bytes", vm_stat_result.stdout)
        page_size = int(page_size_match.group(1)) if page_size_match else 4096
        pages: dict[str, int] = {}
        for raw_line in vm_stat_result.stdout.splitlines():
            if ":" not in raw_line:
                continue
            key, value = raw_line.split(":", 1)
            number = value.strip().strip(".").replace(".", "")
            if number.isdigit():
                pages[key.strip()] = int(number)
        free_pages = pages.get("Pages free", 0)
        inactive_pages = pages.get("Pages inactive", 0)
        speculative_pages = pages.get("Pages speculative", 0)
        free_bytes = free_pages * page_size
        available_bytes = (free_pages + inactive_pages + speculative_pages) * page_size

    return {
        "total_bytes": total_bytes,
        "available_bytes": available_bytes,
        "free_bytes": free_bytes,
    }


def read_interfaces() -> tuple[list[dict[str, object]], CommandResult]:
    """Collect interface inventory via `ifconfig`."""

    result = run_command(["ifconfig"])
    if result.succeeded:
        return parse_ifconfig(result.stdout), result
    return [], result


def read_routes() -> tuple[dict[str, object], CommandResult]:
    """Collect routing data via `netstat -rn` with default-route enrichment."""

    gateway_result = run_command(["route", "-n", "get", "default"])
    gateway_data = (
        parse_route_get_default(gateway_result.stdout)
        if gateway_result.succeeded
        else {
            "default_gateway": None,
            "default_interface": None,
            "has_default_route": False,
            "routes": [],
            "default_route_state": "missing",
            "observations": [],
            "parse_warnings": [],
        }
    )

    table_result = run_command(["netstat", "-rn"])
    if table_result.succeeded:
        route_data = parse_netstat_rn(table_result.stdout)
        if gateway_data["has_default_route"]:
            route_data["default_gateway"] = gateway_data["default_gateway"] or route_data["default_gateway"]
            route_data["default_interface"] = (
                gateway_data["default_interface"] or route_data["default_interface"]
            )
            route_data["has_default_route"] = True
            if not any(route.get("destination") == "default" for route in route_data["routes"]):
                route_data["routes"] = [*gateway_data["routes"], *route_data["routes"]]
        return route_data, table_result

    if gateway_result.succeeded:
        return gateway_data, gateway_result

    return {
        "default_gateway": None,
        "default_interface": None,
        "has_default_route": False,
        "routes": [],
        "default_route_state": "missing",
        "observations": [],
        "parse_warnings": [],
    }, table_result


def read_resolvers() -> list[str]:
    """Read resolver information via `scutil --dns`."""

    result = run_command(["scutil", "--dns"])
    if not result.succeeded:
        return []

    resolvers: list[str] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("nameserver["):
            _, _, value = line.partition(":")
            resolvers.append(value.strip())
    return resolvers


def read_arp_neighbors() -> tuple[list[dict[str, object]], CommandResult]:
    """Collect supplemental ARP cache data."""

    result = run_command(["arp", "-a"])
    if result.succeeded:
        return parse_arp_table(result.stdout), result
    return [], result


def _parse_uptime_seconds(output: str) -> int | None:
    match = re.search(r"\bup\s+(.+?),\s+\d+\s+users?\b", output)
    if not match:
        match = re.search(r"\bup\s+(.+?),\s+load averages?:", output)
        if not match:
            return None

    uptime_text = match.group(1).strip()
    total_seconds = 0

    day_match = re.search(r"(\d+)\s+days?", uptime_text)
    if day_match:
        total_seconds += int(day_match.group(1)) * 86400
        uptime_text = uptime_text.replace(day_match.group(0), "").strip(" ,")

    hour_minute_match = re.search(r"(\d+):(\d+)", uptime_text)
    if hour_minute_match:
        total_seconds += int(hour_minute_match.group(1)) * 3600
        total_seconds += int(hour_minute_match.group(2)) * 60
        return total_seconds

    minute_match = re.search(r"(\d+)\s+mins?", uptime_text)
    if minute_match:
        total_seconds += int(minute_match.group(1)) * 60
        return total_seconds

    hour_match = re.search(r"(\d+)\s+hrs?", uptime_text)
    if hour_match:
        total_seconds += int(hour_match.group(1)) * 3600
        return total_seconds

    return total_seconds or None
