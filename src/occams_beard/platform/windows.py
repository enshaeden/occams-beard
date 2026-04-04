"""Windows-specific collection helpers."""

from __future__ import annotations

import ctypes
import json
from ctypes import wintypes

from occams_beard.utils.parsing import (
    ParsedInterface,
    ParsedNeighbor,
    ParsedRouteData,
    empty_route_data,
    parse_arp_table,
    parse_ipconfig,
    parse_windows_ipconfig_dns_servers,
    parse_powershell_dns_server_list,
    parse_route_print,
)
from occams_beard.utils.subprocess import CommandResult, run_command


class MEMORYSTATUSEX(ctypes.Structure):
    """Windows memory snapshot structure for `GlobalMemoryStatusEx`."""

    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    """Windows power snapshot structure for `GetSystemPowerStatus`."""

    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


def _powershell_json_value(command: str) -> object | None:
    result = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"{command} | ConvertTo-Json -Compress",
        ],
        timeout=8.0,
    )
    if not result.succeeded:
        return None
    if not result.stdout.strip():
        return []

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _powershell_json(command: str) -> dict[str, object] | None:
    payload = _powershell_json_value(command)
    return payload if isinstance(payload, dict) else None


def read_uptime_seconds() -> int | None:
    """Read system uptime using the unprivileged kernel tick counter."""

    try:
        return max(0, int(ctypes.windll.kernel32.GetTickCount64() // 1000))
    except (AttributeError, OSError):
        return None


def read_memory_snapshot() -> dict[str, int | None]:
    """Read memory totals via `GlobalMemoryStatusEx` without elevation."""

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    try:
        succeeded = bool(ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)))
    except (AttributeError, OSError):
        succeeded = False
    if not succeeded:
        return {"total_bytes": None, "available_bytes": None, "free_bytes": None}

    total_bytes = int(status.ullTotalPhys)
    free_bytes = int(status.ullAvailPhys)
    return {
        "total_bytes": total_bytes,
        "available_bytes": free_bytes,
        "free_bytes": free_bytes,
    }


def read_battery_snapshot() -> dict[str, object] | None:
    """Read battery state through `GetSystemPowerStatus` when available."""

    status = SYSTEM_POWER_STATUS()
    try:
        succeeded = bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)))
    except (AttributeError, OSError):
        succeeded = False
    if not succeeded:
        return None

    if _battery_flag_has_no_battery(status.BatteryFlag):
        return {"present": False}

    snapshot: dict[str, object] = {"present": True}
    charge_percent = _normalize_battery_percent(status.BatteryLifePercent)
    if charge_percent is not None:
        snapshot["charge_percent"] = charge_percent

    battery_status = _map_windows_power_status(status)
    if battery_status is not None:
        snapshot["status"] = battery_status
    return snapshot


def read_storage_device_health() -> list[dict[str, object]] | None:
    """Read storage-device health through `Get-PhysicalDisk`."""

    payload = _powershell_json_value(
        "Get-PhysicalDisk | "
        "Select-Object DeviceId,FriendlyName,HealthStatus,OperationalStatus,MediaType"
    )
    records = _as_object_list(payload)
    if payload is None:
        return None

    devices: list[dict[str, object]] = []
    for record in records:
        device_id = _coerce_string(record.get("DeviceId")) or _coerce_string(
            record.get("FriendlyName")
        )
        if device_id is None:
            continue
        devices.append(
            {
                "device_id": device_id,
                "model": _coerce_string(record.get("FriendlyName")),
                "protocol": None,
                "medium": _coerce_string(record.get("MediaType")),
                "health_status": _coerce_string(record.get("HealthStatus")),
                "operational_status": _coerce_string(record.get("OperationalStatus")),
            }
        )
    return devices


def read_interfaces() -> tuple[list[ParsedInterface], CommandResult]:
    """Collect interface inventory via `ipconfig /all`."""

    result = run_command(["ipconfig", "/all"], timeout=8.0)
    if result.succeeded:
        return parse_ipconfig(result.stdout), result
    return [], result


def read_routes() -> tuple[ParsedRouteData, CommandResult]:
    """Collect routing data via `route print`."""

    result = run_command(["route", "print"], timeout=8.0)
    if result.succeeded:
        return parse_route_print(result.stdout), result
    return empty_route_data(), result


def read_resolvers() -> list[str]:
    """Read DNS server information with a PowerShell-first fallback."""

    result = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-DnsClientServerAddress | Select-Object -ExpandProperty ServerAddresses",
        ],
        timeout=8.0,
    )
    if result.succeeded:
        resolvers = parse_powershell_dns_server_list(result.stdout)
        if resolvers:
            return resolvers

    fallback = run_command(["ipconfig", "/all"], timeout=8.0)
    if not fallback.succeeded:
        return []

    return parse_windows_ipconfig_dns_servers(fallback.stdout)


def read_arp_neighbors() -> tuple[list[ParsedNeighbor], CommandResult]:
    """Collect supplemental ARP cache data."""

    result = run_command(["arp", "-a"], timeout=8.0)
    if result.succeeded:
        return parse_arp_table(result.stdout), result
    return [], result


def _as_object_list(payload: object | None) -> list[dict[str, object]]:
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _coerce_int(value: object) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _coerce_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _map_windows_battery_status(status_code: int | None) -> str | None:
    if status_code == 1:
        return "Discharging"
    if status_code == 2:
        return "On AC power"
    if status_code == 3:
        return "Fully charged"
    if status_code == 6:
        return "Charging"
    if status_code == 11:
        return "Partially charged"
    return None


def _normalize_battery_percent(raw_percent: int) -> int | None:
    if raw_percent == 255:
        return None
    return raw_percent


def _battery_flag_has_no_battery(flag: int) -> bool:
    return bool(flag & 128)


def _map_windows_power_status(status: SYSTEM_POWER_STATUS) -> str | None:
    if status.BatteryFlag & 8:
        return "Charging"
    if status.ACLineStatus == 1 and status.BatteryLifePercent == 100:
        return "Fully charged"
    if status.ACLineStatus == 1:
        return "On AC power"
    if status.ACLineStatus == 0:
        return "Discharging"
    return None
