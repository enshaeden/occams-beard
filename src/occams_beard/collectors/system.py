"""Collectors for host basics and resource state."""

from __future__ import annotations

import getpass
import logging
import os
import platform as python_platform
from collections import defaultdict
from collections.abc import Callable

from occams_beard.models import (
    BatteryState,
    CpuState,
    DiagnosticWarning,
    HostBasics,
    MemoryState,
    ProcessCategoryLoad,
    ProcessSnapshot,
)
from occams_beard.platform import current_platform, linux, macos, windows

LOGGER = logging.getLogger(__name__)

_PROCESS_CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "browser": (
        "arc",
        "brave",
        "chrome",
        "chromium",
        "edge",
        "firefox",
        "msedge",
        "opera",
        "safari",
    ),
    "ide": (
        "androidstudio",
        "clion",
        "code",
        "cursor",
        "eclipse",
        "goland",
        "idea",
        "phpstorm",
        "pycharm",
        "rubymine",
        "studio64",
        "webstorm",
        "zed",
    ),
    "vm": (
        "hyperkit",
        "multipassd",
        "parallels",
        "prl_vm_app",
        "qemu",
        "utm",
        "virtualboxvm",
        "vmware",
        "vmmem",
    ),
    "container_runtime": (
        "colima",
        "com.docker.backend",
        "containerd",
        "dockerd",
        "docker",
        "lima",
        "minikube",
        "podman",
        "rancher-desktop",
    ),
    "database": (
        "mongod",
        "mysqld",
        "postgres",
        "postgresql",
        "redis-server",
        "sqlservr",
    ),
    "collaboration": (
        "discord",
        "slack",
        "teams",
        "webex",
        "zoom",
    ),
}


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
) -> tuple[
    CpuState,
    MemoryState,
    BatteryState | None,
    ProcessSnapshot | None,
    list[DiagnosticWarning],
]:
    """Collect CPU, memory, and battery facts."""

    warnings: list[DiagnosticWarning] = []
    cpu_state = CpuState(logical_cpus=os.cpu_count())
    platform_name = current_platform()

    if hasattr(os, "getloadavg"):
        try:
            load_1m, load_5m, load_15m = os.getloadavg()
            cpu_state.load_average_1m = load_1m
            cpu_state.load_average_5m = load_5m
            cpu_state.load_average_15m = load_15m
            if cpu_state.logical_cpus:
                cpu_state.load_ratio_1m = round(load_1m / cpu_state.logical_cpus, 2)
                cpu_state.utilization_percent_estimate = round(
                    min((load_1m / cpu_state.logical_cpus) * 100, 1000.0),
                    1,
                )
                cpu_state.saturation_level = _classify_cpu_saturation(
                    load_ratio_1m=cpu_state.load_ratio_1m,
                    load_average_5m=load_5m,
                    logical_cpus=cpu_state.logical_cpus,
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
    elif current_platform() != "windows":
        warnings.append(
            DiagnosticWarning(
                domain="resources",
                code="load-average-unsupported",
                message="Load average is not supported on this platform.",
            )
        )
    if progress_callback is not None:
        progress_callback(1)

    if platform_name == "linux":
        memory_data = linux.read_memory_snapshot()
        battery_data = linux.read_battery_snapshot()
        process_data = linux.read_process_snapshot()
    elif platform_name == "macos":
        memory_data = macos.read_memory_snapshot()
        battery_data = macos.read_battery_snapshot()
        process_data = macos.read_process_snapshot()
    elif platform_name == "windows":
        memory_data = windows.read_memory_snapshot()
        battery_data = windows.read_battery_snapshot()
        process_data = windows.read_process_snapshot()
    else:
        memory_data = {
            "total_bytes": None,
            "available_bytes": None,
            "free_bytes": None,
            "swap_total_bytes": None,
            "swap_free_bytes": None,
            "swap_used_bytes": None,
            "committed_bytes": None,
            "commit_limit_bytes": None,
        }
        battery_data = None
        process_data = None
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

    available_percent = _available_percent(
        total_bytes=memory_data["total_bytes"],
        available_bytes=memory_data["available_bytes"],
    )
    memory_state = MemoryState(
        total_bytes=memory_data["total_bytes"],
        available_bytes=memory_data["available_bytes"],
        free_bytes=memory_data["free_bytes"],
        pressure_level=_classify_memory_pressure(
            total_bytes=memory_data["total_bytes"],
            available_bytes=memory_data["available_bytes"],
        ),
        available_percent=available_percent,
        swap_total_bytes=_coerce_int(memory_data.get("swap_total_bytes")),
        swap_free_bytes=_coerce_int(memory_data.get("swap_free_bytes")),
        swap_used_bytes=_coerce_int(memory_data.get("swap_used_bytes")),
        committed_bytes=_coerce_int(memory_data.get("committed_bytes")),
        commit_limit_bytes=_coerce_int(memory_data.get("commit_limit_bytes")),
        commit_pressure_level=_classify_commit_pressure(
            committed_bytes=_coerce_int(memory_data.get("committed_bytes")),
            commit_limit_bytes=_coerce_int(memory_data.get("commit_limit_bytes")),
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

    process_snapshot = _build_process_snapshot(
        process_data,
        total_memory_bytes=memory_state.total_bytes,
    )
    if process_data is None and platform_name in {"linux", "macos", "windows"}:
        warnings.append(
            DiagnosticWarning(
                domain="resources",
                code="process-snapshot-unavailable",
                message="Bounded process-load hints could not be collected on this endpoint.",
            )
        )
    if progress_callback is not None:
        progress_callback(3)
    return cpu_state, memory_state, battery_state, process_snapshot, warnings


def _classify_cpu_saturation(
    *,
    load_ratio_1m: float | None,
    load_average_5m: float | None,
    logical_cpus: int | None,
) -> str | None:
    if load_ratio_1m is None or logical_cpus is None or logical_cpus <= 0:
        return None

    sustained_ratio = (
        load_average_5m / logical_cpus if load_average_5m is not None else load_ratio_1m
    )
    if load_ratio_1m >= 1.25 and sustained_ratio >= 1.0:
        return "high"
    if load_ratio_1m >= 0.85 or sustained_ratio >= 0.75:
        return "elevated"
    return "normal"


def _classify_memory_pressure(total_bytes: int | None, available_bytes: int | None) -> str | None:
    if total_bytes is None or available_bytes is None or total_bytes <= 0:
        return None

    ratio = available_bytes / total_bytes
    if ratio <= 0.10:
        return "high"
    if ratio <= 0.20:
        return "elevated"
    return "normal"


def _available_percent(total_bytes: int | None, available_bytes: int | None) -> float | None:
    if total_bytes is None or available_bytes is None or total_bytes <= 0:
        return None
    return round((available_bytes / total_bytes) * 100, 1)


def _classify_commit_pressure(
    *,
    committed_bytes: int | None,
    commit_limit_bytes: int | None,
) -> str | None:
    if (
        committed_bytes is None
        or commit_limit_bytes is None
        or commit_limit_bytes <= 0
        or committed_bytes < 0
    ):
        return None

    ratio = committed_bytes / commit_limit_bytes
    if ratio >= 0.95:
        return "high"
    if ratio >= 0.85:
        return "elevated"
    return "normal"


def _build_process_snapshot(
    process_data: list[dict[str, object]] | None,
    *,
    total_memory_bytes: int | None,
) -> ProcessSnapshot | None:
    if process_data is None:
        return None

    normalized_processes: list[dict[str, object]] = []
    high_cpu_process_count = 0
    high_memory_process_count = 0
    high_memory_threshold = max(512 * 1024**2, int((total_memory_bytes or 0) * 0.10))

    for record in process_data:
        name = _normalize_process_name(record.get("name"))
        if name is None:
            continue
        cpu_percent = _coerce_float(record.get("cpu_percent_estimate"))
        memory_bytes = _coerce_int(record.get("memory_bytes"))
        category = _categorize_process(name)
        memory_score = (
            (memory_bytes / total_memory_bytes) * 100
            if memory_bytes is not None and total_memory_bytes
            else 0.0
        )
        score = max(cpu_percent or 0.0, memory_score)

        if cpu_percent is not None and cpu_percent >= 50.0:
            high_cpu_process_count += 1
        if (
            memory_bytes is not None
            and high_memory_threshold > 0
            and memory_bytes >= high_memory_threshold
        ):
            high_memory_process_count += 1

        normalized_processes.append(
            {
                "category": category,
                "cpu_percent_estimate": cpu_percent,
                "memory_bytes": memory_bytes,
                "score": score,
            }
        )

    notable_processes = [
        item
        for item in sorted(
            normalized_processes,
            key=lambda item: (
                _coerce_float(item.get("score")) or 0.0,
                _coerce_float(item.get("cpu_percent_estimate")) or 0.0,
                _coerce_int(item.get("memory_bytes")) or 0,
            ),
            reverse=True,
        )[:12]
        if (item["category"] != "other") or ((_coerce_float(item.get("score")) or 0.0) >= 10.0)
    ]

    category_totals: dict[str, dict[str, float | int | None]] = defaultdict(
        lambda: {
            "process_count": 0,
            "combined_cpu": 0.0,
            "peak_cpu": None,
            "combined_memory": 0,
            "peak_memory": None,
        }
    )
    for item in notable_processes:
        totals = category_totals[str(item["category"])]
        totals["process_count"] = int(totals["process_count"] or 0) + 1

        cpu_percent = _coerce_float(item.get("cpu_percent_estimate"))
        if cpu_percent is not None:
            totals["combined_cpu"] = float(totals["combined_cpu"] or 0.0) + cpu_percent
            prior_peak_cpu = _coerce_float(totals.get("peak_cpu"))
            totals["peak_cpu"] = (
                cpu_percent if prior_peak_cpu is None else max(prior_peak_cpu, cpu_percent)
            )

        memory_bytes = _coerce_int(item.get("memory_bytes"))
        if memory_bytes is not None:
            totals["combined_memory"] = int(totals["combined_memory"] or 0) + memory_bytes
            prior_peak_memory = _coerce_int(totals.get("peak_memory"))
            totals["peak_memory"] = (
                memory_bytes if prior_peak_memory is None else max(prior_peak_memory, memory_bytes)
            )

    top_categories = sorted(
        (
            ProcessCategoryLoad(
                category=category,
                process_count=int(values["process_count"] or 0),
                combined_cpu_percent_estimate=round(float(values["combined_cpu"]), 1)
                if values["combined_cpu"]
                else None,
                peak_cpu_percent_estimate=round(_coerce_float(values["peak_cpu"]) or 0.0, 1)
                if values["peak_cpu"] is not None
                else None,
                combined_memory_bytes=(
                    int(values["combined_memory"]) if values["combined_memory"] else None
                ),
                peak_memory_bytes=_coerce_int(values["peak_memory"]),
            )
            for category, values in category_totals.items()
            if values["process_count"]
        ),
        key=lambda item: (
            item.combined_cpu_percent_estimate or 0.0,
            (
                (item.combined_memory_bytes / total_memory_bytes) * 100
                if item.combined_memory_bytes is not None and total_memory_bytes
                else 0.0
            ),
            item.process_count,
        ),
        reverse=True,
    )[:3]

    return ProcessSnapshot(
        sampled_process_count=len(normalized_processes),
        high_cpu_process_count=high_cpu_process_count,
        high_memory_process_count=high_memory_process_count,
        top_categories=top_categories,
    )


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
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _coerce_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _coerce_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _normalize_process_name(value: object) -> str | None:
    name = _coerce_string(value)
    if name is None:
        return None
    return name.rsplit("/", 1)[-1].removesuffix(".exe").lower()


def _categorize_process(name: str) -> str:
    for category, patterns in _PROCESS_CATEGORY_PATTERNS.items():
        if any(
            name == pattern
            or name.startswith(f"{pattern}-")
            or f" {pattern}" in name
            or pattern in name
            for pattern in patterns
        ):
            return category
    return "other"
