"""macOS-specific collection helpers."""

from __future__ import annotations

import re
from datetime import datetime

from occams_beard.utils.parsing import (
    ParsedInterface,
    ParsedNeighbor,
    ParsedRouteData,
    empty_route_data,
    parse_arp_table,
    parse_ifconfig,
    parse_netstat_rn,
    parse_route_get_default,
    parse_scutil_dns,
)
from occams_beard.utils.subprocess import CommandResult, run_command


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
    swap_result = run_command(["sysctl", "vm.swapusage"])
    total_bytes = int(total_result.stdout.strip()) if total_result.succeeded else None
    free_bytes = None
    available_bytes = None
    swap_total_bytes = None
    swap_free_bytes = None
    swap_used_bytes = None

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

    if swap_result.succeeded:
        swap_usage = _parse_swapusage_bytes(swap_result.stdout)
        if swap_usage is not None:
            swap_total_bytes = swap_usage["total_bytes"]
            swap_used_bytes = swap_usage["used_bytes"]
            swap_free_bytes = swap_usage["free_bytes"]

    return {
        "total_bytes": total_bytes,
        "available_bytes": available_bytes,
        "free_bytes": free_bytes,
        "swap_total_bytes": swap_total_bytes,
        "swap_free_bytes": swap_free_bytes,
        "swap_used_bytes": swap_used_bytes,
        "committed_bytes": None,
        "commit_limit_bytes": None,
    }


def read_battery_snapshot() -> dict[str, object] | None:
    """Read battery health information from built-in macOS commands."""

    profiler_result = run_command(["system_profiler", "SPPowerDataType"], timeout=8.0)
    pmset_result = run_command(["pmset", "-g", "batt"], timeout=8.0)

    profiler_snapshot = (
        _parse_system_profiler_battery(profiler_result.stdout)
        if profiler_result.succeeded
        else None
    )
    pmset_snapshot = _parse_pmset_battery(pmset_result.stdout) if pmset_result.succeeded else None

    if _snapshot_marks_battery_absent(profiler_snapshot) or _snapshot_marks_battery_absent(
        pmset_snapshot
    ):
        return {"present": False}
    if profiler_snapshot is None and pmset_snapshot is None:
        return None

    snapshot: dict[str, object] = {"present": True}
    for source in (profiler_snapshot, pmset_snapshot):
        if source is None:
            continue
        for key, value in source.items():
            if key == "present" or value is None:
                continue
            snapshot[key] = value
    return snapshot


def read_storage_device_health() -> list[dict[str, object]] | None:
    """Read storage-device health information from `diskutil info -all`."""

    result = run_command(["diskutil", "info", "-all"], timeout=8.0)
    if not result.succeeded:
        return None
    return _parse_diskutil_storage_devices(result.stdout)


def read_process_snapshot() -> list[dict[str, object]] | None:
    """Collect a bounded process snapshot from `ps` without persisting raw output."""

    result = run_command(
        ["ps", "-A", "-o", "comm=,pcpu=,rss="],
        timeout=6.0,
        capture_output_for_bundle=False,
    )
    if not result.succeeded:
        return None

    processes: list[dict[str, object]] = []
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        command, cpu_text, rss_text = parts
        try:
            cpu_percent = float(cpu_text)
            rss_kib = int(rss_text)
        except ValueError:
            continue
        processes.append(
            {
                "name": command,
                "cpu_percent_estimate": round(cpu_percent, 1),
                "memory_bytes": rss_kib * 1024,
            }
        )
    return processes


def read_interfaces() -> tuple[list[ParsedInterface], CommandResult]:
    """Collect interface inventory via `ifconfig`."""

    result = run_command(["ifconfig"])
    if result.succeeded:
        return parse_ifconfig(result.stdout), result
    return [], result


def read_routes() -> tuple[ParsedRouteData, CommandResult]:
    """Collect routing data via `netstat -rn` with default-route enrichment."""

    gateway_result = run_command(["route", "-n", "get", "default"])
    gateway_data = (
        parse_route_get_default(gateway_result.stdout)
        if gateway_result.succeeded
        else empty_route_data()
    )

    table_result = run_command(["netstat", "-rn"])
    if table_result.succeeded:
        route_data = parse_netstat_rn(table_result.stdout)
        if gateway_data["has_default_route"]:
            route_data["default_gateway"] = (
                gateway_data["default_gateway"] or route_data["default_gateway"]
            )
            route_data["default_interface"] = (
                gateway_data["default_interface"] or route_data["default_interface"]
            )
            route_data["has_default_route"] = True
            if not any(route["destination"] == "default" for route in route_data["routes"]):
                route_data["routes"] = [*gateway_data["routes"], *route_data["routes"]]
        return route_data, table_result

    if gateway_result.succeeded:
        return gateway_data, gateway_result

    return empty_route_data(), table_result


def read_resolvers() -> list[str]:
    """Read resolver information via `scutil --dns`."""

    result = run_command(["scutil", "--dns"])
    if not result.succeeded:
        return []
    return parse_scutil_dns(result.stdout)


def read_arp_neighbors() -> tuple[list[ParsedNeighbor], CommandResult]:
    """Collect supplemental ARP cache data."""

    result = run_command(["arp", "-an"], timeout=3.0)
    if result.succeeded:
        return parse_arp_table(result.stdout), result
    return [], result


def _parse_system_profiler_battery(output: str) -> dict[str, object] | None:
    lowered = output.lower()
    if "no battery information found" in lowered or "no batteries available" in lowered:
        return {"present": False}

    snapshot: dict[str, object] = {}
    charge_match = re.search(r"^\s*State of Charge \(%\):\s*(\d+)\s*$", output, re.MULTILINE)
    if charge_match:
        snapshot["charge_percent"] = int(charge_match.group(1))

    cycle_match = re.search(r"^\s*Cycle Count:\s*(\d+)\s*$", output, re.MULTILINE)
    if cycle_match:
        snapshot["cycle_count"] = int(cycle_match.group(1))

    condition_match = re.search(r"^\s*Condition:\s*(.+?)\s*$", output, re.MULTILINE)
    if condition_match:
        snapshot["condition"] = condition_match.group(1).strip()

    maximum_capacity_match = re.search(
        r"^\s*Maximum Capacity:\s*([\d.]+)%\s*$",
        output,
        re.MULTILINE,
    )
    if maximum_capacity_match:
        snapshot["health_percent"] = float(maximum_capacity_match.group(1))

    if snapshot:
        snapshot["present"] = True
        return snapshot
    return None


def _parse_pmset_battery(output: str) -> dict[str, object] | None:
    lowered = output.lower()
    if "no batteries" in lowered or "no battery" in lowered:
        return {"present": False}

    match = re.search(r"(\d+)%;\s*([^;]+);", output)
    if not match:
        return None

    return {
        "present": True,
        "charge_percent": int(match.group(1)),
        "status": match.group(2).strip(),
    }


def _parse_diskutil_storage_devices(output: str) -> list[dict[str, object]]:
    devices: list[dict[str, object]] = []
    for block in re.split(r"\n\s*\n", output.strip()):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()

        device_id = fields.get("Device Identifier")
        if not device_id:
            continue

        part_of_whole = fields.get("Part of Whole")
        if part_of_whole and part_of_whole != device_id:
            continue

        model = fields.get("Device / Media Name") or fields.get("Media Name")
        protocol = fields.get("Protocol")
        health_status = fields.get("SMART Status")
        if fields.get("Solid State") == "Yes":
            medium = "SSD"
        elif fields.get("Solid State") == "No":
            medium = "HDD"
        else:
            medium = None

        if not any((model, protocol, health_status, medium)):
            continue

        devices.append(
            {
                "device_id": device_id,
                "model": model,
                "protocol": protocol,
                "medium": medium,
                "health_status": health_status,
                "operational_status": None,
            }
        )
    return devices


def _parse_swapusage_bytes(output: str) -> dict[str, int] | None:
    match = re.search(
        r"total = ([\d.]+[BKMGTP])\s+used = ([\d.]+[BKMGTP])\s+free = ([\d.]+[BKMGTP])",
        output,
    )
    if not match:
        return None

    return {
        "total_bytes": _parse_size_token(match.group(1)),
        "used_bytes": _parse_size_token(match.group(2)),
        "free_bytes": _parse_size_token(match.group(3)),
    }


def _parse_size_token(value: str) -> int:
    number = float(value[:-1])
    suffix = value[-1].upper()
    multipliers = {
        "B": 1,
        "K": 1024,
        "M": 1024**2,
        "G": 1024**3,
        "T": 1024**4,
        "P": 1024**5,
    }
    return int(number * multipliers[suffix])


def _snapshot_marks_battery_absent(snapshot: dict[str, object] | None) -> bool:
    return snapshot is not None and snapshot.get("present") is False


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
