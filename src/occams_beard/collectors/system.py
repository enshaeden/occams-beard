"""Collectors for host basics and resource state."""

from __future__ import annotations

import getpass
import logging
import os
import platform as python_platform
from collections.abc import Callable

from occams_beard.models import BatteryState, CpuState, DiagnosticWarning, HostBasics, MemoryState
from occams_beard.platform import current_platform, linux, macos, windows

LOGGER = logging.getLogger(__name__)


def collect_host_basics() -> tuple[HostBasics, list[DiagnosticWarning]]:
    """Collect basic endpoint facts."""

    warnings: list[DiagnosticWarning] = []
    system = python_platform.system()
    platform_name = current_platform()

    uptime_seconds = None
    if platform_name == "linux":
        uptime_seconds = linux.read_uptime_seconds()
    elif platform_name == "macos":
        uptime_seconds = macos.read_uptime_seconds()
    elif platform_name == "windows":
        uptime_seconds = windows.read_uptime_seconds()
    else:
        warnings.append(
            DiagnosticWarning(
                domain="host",
                code="unsupported-platform",
                message=f"Unsupported platform for uptime collection: {platform_name}",
            )
        )
    if uptime_seconds is None and platform_name in {"linux", "macos", "windows"}:
        warnings.append(
            DiagnosticWarning(
                domain="host",
                code="uptime-unavailable",
                message="System uptime could not be determined on this endpoint.",
            )
        )

    try:
        current_user = getpass.getuser()
    except OSError:
        current_user = None
        warnings.append(
            DiagnosticWarning(
                domain="host",
                code="user-unavailable",
                message="Current user could not be determined.",
            )
        )

    host = HostBasics(
        hostname=python_platform.node(),
        operating_system=system,
        kernel=python_platform.release(),
        current_user=current_user,
        uptime_seconds=uptime_seconds,
    )
    return host, warnings


def collect_resource_state(
    *,
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[CpuState, MemoryState, BatteryState | None, list[DiagnosticWarning]]:
    """Collect CPU, memory, and battery facts."""

    warnings: list[DiagnosticWarning] = []
    cpu_state = CpuState(logical_cpus=os.cpu_count())

    if hasattr(os, "getloadavg"):
        try:
            load_1m, load_5m, load_15m = os.getloadavg()
            cpu_state.load_average_1m = load_1m
            cpu_state.load_average_5m = load_5m
            cpu_state.load_average_15m = load_15m
            if cpu_state.logical_cpus:
                cpu_state.utilization_percent_estimate = round(
                    min((load_1m / cpu_state.logical_cpus) * 100, 1000.0),
                    1,
                )
        except OSError as exc:
            LOGGER.debug("Unable to collect load average: %s", exc)
            warnings.append(
                DiagnosticWarning(
                    domain="resources",
                    code="load-average-unavailable",
                    message="Load average is unavailable on this endpoint.",
                )
            )
    else:
        warnings.append(
            DiagnosticWarning(
                domain="resources",
                code="load-average-unsupported",
                message="Load average is not supported on this platform.",
            )
        )
    if progress_callback is not None:
        progress_callback(1)

    platform_name = current_platform()
    if platform_name == "linux":
        memory_data = linux.read_memory_snapshot()
        battery_data = linux.read_battery_snapshot()
    elif platform_name == "macos":
        memory_data = macos.read_memory_snapshot()
        battery_data = macos.read_battery_snapshot()
    elif platform_name == "windows":
        memory_data = windows.read_memory_snapshot()
        battery_data = windows.read_battery_snapshot()
    else:
        memory_data = {"total_bytes": None, "available_bytes": None, "free_bytes": None}
        battery_data = None
        warnings.append(
            DiagnosticWarning(
                domain="resources",
                code="memory-unsupported",
                message=f"Memory collection is unsupported on platform: {platform_name}",
            )
        )
    if memory_data["total_bytes"] is None and platform_name in {"linux", "macos", "windows"}:
        warnings.append(
            DiagnosticWarning(
                domain="resources",
                code="memory-unavailable",
                message="Memory totals could not be determined on this endpoint.",
            )
        )

    memory_state = MemoryState(
        total_bytes=memory_data["total_bytes"],
        available_bytes=memory_data["available_bytes"],
        free_bytes=memory_data["free_bytes"],
        pressure_level=_classify_memory_pressure(
            total_bytes=memory_data["total_bytes"],
            available_bytes=memory_data["available_bytes"],
        ),
    )
    battery_state = _build_battery_state(battery_data)
    if battery_data is None and platform_name in {"linux", "macos", "windows"}:
        warnings.append(
            DiagnosticWarning(
                domain="resources",
                code="battery-unavailable",
                message="Battery health facts could not be collected on this endpoint.",
            )
        )
    if progress_callback is not None:
        progress_callback(2)
    return cpu_state, memory_state, battery_state, warnings


def _classify_memory_pressure(total_bytes: int | None, available_bytes: int | None) -> str | None:
    if total_bytes is None or available_bytes is None or total_bytes <= 0:
        return None

    ratio = available_bytes / total_bytes
    if ratio <= 0.10:
        return "high"
    if ratio <= 0.20:
        return "elevated"
    return "normal"


def _build_battery_state(battery_data: dict[str, object] | None) -> BatteryState | None:
    if battery_data is None:
        return None
    return BatteryState(
        present=bool(battery_data.get("present", False)),
        charge_percent=_coerce_int(battery_data.get("charge_percent")),
        status=_coerce_string(battery_data.get("status")),
        cycle_count=_coerce_int(battery_data.get("cycle_count")),
        condition=_coerce_string(battery_data.get("condition")),
        health_percent=_coerce_float(battery_data.get("health_percent")),
    )


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _coerce_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _coerce_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None
