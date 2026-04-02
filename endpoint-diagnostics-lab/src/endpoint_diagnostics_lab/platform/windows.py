"""Windows-specific collection helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from endpoint_diagnostics_lab.utils.parsing import parse_ipconfig, parse_route_print
from endpoint_diagnostics_lab.utils.subprocess import CommandResult, run_command


def _powershell_json(command: str) -> dict[str, object] | None:
    result = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"{command} | ConvertTo-Json -Compress",
        ],
        timeout=8.0,
    )
    if not result.succeeded or not result.stdout.strip():
        return None

    try:
        loaded = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    return loaded if isinstance(loaded, dict) else None


def read_uptime_seconds() -> int | None:
    """Read system uptime using PowerShell CIM APIs."""

    payload = _powershell_json("Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime")
    if payload is None:
        return None

    boot_text = payload.get("LastBootUpTime")
    if not isinstance(boot_text, str):
        return None

    try:
        boot_time = datetime.fromisoformat(boot_text.replace("Z", "+00:00"))
    except ValueError:
        return None

    return max(0, int((datetime.now(timezone.utc) - boot_time.astimezone(timezone.utc)).total_seconds()))


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


def read_interfaces() -> tuple[list[dict[str, object]], CommandResult]:
    """Collect interface inventory via `ipconfig /all`."""

    result = run_command(["ipconfig", "/all"], timeout=8.0)
    if result.succeeded:
        return parse_ipconfig(result.stdout), result
    return [], result


def read_routes() -> tuple[dict[str, object], CommandResult]:
    """Collect routing data via `route print`."""

    result = run_command(["route", "print"], timeout=8.0)
    if result.succeeded:
        return parse_route_print(result.stdout), result
    return {
        "default_gateway": None,
        "default_interface": None,
        "has_default_route": False,
        "routes": [],
    }, result


def read_resolvers() -> list[str]:
    """Read DNS server information via PowerShell."""

    result = run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-DnsClientServerAddress -AddressFamily IPv4 | "
            "Select-Object -ExpandProperty ServerAddresses",
        ],
        timeout=8.0,
    )
    if not result.succeeded:
        return []

    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
