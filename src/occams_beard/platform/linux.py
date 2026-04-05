"""Linux-specific collection helpers."""

from __future__ import annotations

from pathlib import Path

from occams_beard.utils.parsing import (
    ParsedInterface,
    ParsedNeighbor,
    ParsedRouteData,
    empty_route_data,
    parse_arp_table,
    parse_ip_addr_show,
    parse_ip_neigh,
    parse_linux_ip_route,
    parse_netstat_rn,
    parse_resolv_conf,
)
from occams_beard.utils.subprocess import CommandResult, run_command


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
        return {
            "total_bytes": None,
            "available_bytes": None,
            "free_bytes": None,
            "swap_total_bytes": None,
            "swap_free_bytes": None,
            "swap_used_bytes": None,
            "committed_bytes": None,
            "commit_limit_bytes": None,
        }

    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        number = value.strip().split()[0]
        if number.isdigit():
            values[key] = int(number) * 1024

    swap_total = values.get("SwapTotal")
    swap_free = values.get("SwapFree")
    swap_used = None
    if swap_total is not None and swap_free is not None:
        swap_used = max(swap_total - swap_free, 0)

    return {
        "total_bytes": values.get("MemTotal"),
        "available_bytes": values.get("MemAvailable", values.get("MemFree")),
        "free_bytes": values.get("MemFree"),
        "swap_total_bytes": swap_total,
        "swap_free_bytes": swap_free,
        "swap_used_bytes": swap_used,
        "committed_bytes": values.get("Committed_AS"),
        "commit_limit_bytes": values.get("CommitLimit"),
    }


def read_battery_snapshot() -> dict[str, object] | None:
    """Read battery health information from sysfs when available."""

    power_root = Path("/sys/class/power_supply")
    if not power_root.exists():
        return {"present": False}

    batteries = sorted(path for path in power_root.iterdir() if path.name.startswith("BAT"))
    if not batteries:
        return {"present": False}

    battery_root = batteries[0]
    present_value = _read_sysfs_text(battery_root / "present")
    if present_value == "0":
        return {"present": False}

    snapshot: dict[str, object] = {"present": True}
    charge_percent = _read_sysfs_int(battery_root / "capacity")
    if charge_percent is not None:
        snapshot["charge_percent"] = charge_percent

    status = _read_sysfs_text(battery_root / "status")
    if status:
        snapshot["status"] = status

    cycle_count = _read_sysfs_int(battery_root / "cycle_count")
    if cycle_count is not None:
        snapshot["cycle_count"] = cycle_count

    condition = _read_sysfs_text(battery_root / "health") or _read_sysfs_text(
        battery_root / "capacity_level"
    )
    if condition:
        snapshot["condition"] = condition

    health_percent = _read_battery_health_percent(battery_root)
    if health_percent is not None:
        snapshot["health_percent"] = health_percent
    return snapshot


def read_storage_device_health() -> list[dict[str, object]]:
    """Return non-privileged storage-device health data when available."""

    return []


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
    """Collect interface inventory."""

    result = run_command(["ip", "addr", "show"])
    if result.succeeded:
        return parse_ip_addr_show(result.stdout), result

    fallback = run_command(["ifconfig"])
    if fallback.succeeded:
        from occams_beard.utils.parsing import parse_ifconfig

        return parse_ifconfig(fallback.stdout), fallback
    return [], fallback


def read_routes() -> tuple[ParsedRouteData, CommandResult]:
    """Collect route inventory."""

    result = run_command(["ip", "route", "show"])
    if result.succeeded:
        return parse_linux_ip_route(result.stdout), result

    fallback = run_command(["netstat", "-rn"])
    if fallback.succeeded:
        return parse_netstat_rn(fallback.stdout), fallback
    return empty_route_data(), fallback


def read_arp_neighbors() -> tuple[list[ParsedNeighbor], CommandResult]:
    """Collect supplemental ARP or neighbor-cache data."""

    result = run_command(["ip", "neigh", "show"])
    if result.succeeded:
        return parse_ip_neigh(result.stdout), result

    fallback = run_command(["arp", "-an"], timeout=3.0)
    if fallback.succeeded:
        return parse_arp_table(fallback.stdout), fallback
    return [], fallback


def read_resolvers() -> list[str]:
    """Read resolvers from `/etc/resolv.conf`."""

    path = Path("/etc/resolv.conf")
    if not path.exists():
        return []
    return parse_resolv_conf(path.read_text(encoding="utf-8"))


def _read_battery_health_percent(battery_root: Path) -> float | None:
    full_value = _read_sysfs_int(battery_root / "energy_full")
    design_value = _read_sysfs_int(battery_root / "energy_full_design")
    if full_value is None or design_value is None or design_value == 0:
        full_value = _read_sysfs_int(battery_root / "charge_full")
        design_value = _read_sysfs_int(battery_root / "charge_full_design")
    if full_value is None or design_value is None or design_value == 0:
        return None
    return round((full_value / design_value) * 100, 1)


def _read_sysfs_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _read_sysfs_int(path: Path) -> int | None:
    value = _read_sysfs_text(path)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
