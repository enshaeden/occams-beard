"""Windows-specific collection helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from occams_beard.utils.parsing import (
    ParsedInterface,
    ParsedNeighbor,
    ParsedRouteData,
    empty_route_data,
    parse_arp_table,
    parse_ipconfig,
    parse_powershell_dns_server_list,
    parse_route_print,
)
from occams_beard.utils.subprocess import CommandResult, run_command


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
    """Read system uptime using PowerShell CIM APIs."""

    payload = _powershell_json(
        "Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime"
    )
    if payload is None:
        return None

    boot_text = payload.get("LastBootUpTime")
    if not isinstance(boot_text, str):
        return None

    try:
        boot_time = datetime.fromisoformat(boot_text.replace("Z", "+00:00"))
    except ValueError:
        return None

    return max(0, int((datetime.now(UTC) - boot_time.astimezone(UTC)).total_seconds()))


def read_memory_snapshot() -> dict[str, int | None]:
    """Read memory totals via PowerShell CIM APIs."""

    payload = _powershell_json(
        "Get-CimInstance Win32_OperatingSystem | "
        "Select-Object TotalVisibleMemorySize,FreePhysicalMemory"
    )
    if payload is None:
        return {"total_bytes": None, "available_bytes": None, "free_bytes": None}

    total_kib = payload.get("TotalVisibleMemorySize")
    free_kib = payload.get("FreePhysicalMemory")
    total_bytes = int(total_kib) * 1024 if isinstance(total_kib, (int, float)) else None
    free_bytes = int(free_kib) * 1024 if isinstance(free_kib, (int, float)) else None
    return {
        "total_bytes": total_bytes,
        "available_bytes": free_bytes,
        "free_bytes": free_bytes,
    }


def read_battery_snapshot() -> dict[str, object] | None:
    """Read battery state through Win32_Battery when available."""

    payload = _powershell_json_value(
        "Get-CimInstance Win32_Battery | "
        "Select-Object EstimatedChargeRemaining,BatteryStatus,Status"
    )
    records = _as_object_list(payload)
    if payload is None:
        return None
    if not records:
        return {"present": False}

    battery = records[0]
    snapshot: dict[str, object] = {"present": True}
    charge_percent = _coerce_int(battery.get("EstimatedChargeRemaining"))
    if charge_percent is not None:
        snapshot["charge_percent"] = charge_percent

    status = _coerce_string(battery.get("Status")) or _map_windows_battery_status(
        _coerce_int(battery.get("BatteryStatus"))
    )
    if status is not None:
        snapshot["status"] = status
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
    """Read DNS server information via PowerShell."""

    result = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-DnsClientServerAddress | Select-Object -ExpandProperty ServerAddresses",
        ],
        timeout=8.0,
    )
    if not result.succeeded:
        return []

    return parse_powershell_dns_server_list(result.stdout)


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
