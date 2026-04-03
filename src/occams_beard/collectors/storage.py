"""Collectors for disk and filesystem usage."""

from __future__ import annotations

import logging
import os
import shutil
import string
from collections.abc import Callable

from occams_beard.models import DiagnosticWarning, DiskVolume, StorageDeviceHealth
from occams_beard.platform import current_platform, linux, macos, windows
from occams_beard.utils.subprocess import run_command

LOGGER = logging.getLogger(__name__)

_MACOS_IGNORED_MOUNT_POINTS = frozenset(
    {
        "/dev",
    }
)
_MACOS_IGNORED_MOUNT_PREFIXES = ("/Library/Developer/CoreSimulator/Volumes/",)


def collect_storage_state(
    *,
    progress_callback: Callable[[int], None] | None = None,
) -> tuple[list[DiskVolume], list[StorageDeviceHealth], list[DiagnosticWarning]]:
    """Collect relevant volume usage and non-privileged device health information."""

    warnings: list[DiagnosticWarning] = []
    mount_points = _discover_mount_points()
    disks: list[DiskVolume] = []

    for path in mount_points:
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            warnings.append(
                DiagnosticWarning(
                    domain="storage",
                    code="disk-usage-failed",
                    message=f"Disk usage could not be collected for path: {path}",
                )
            )
            continue

        percent_used = round((usage.used / usage.total) * 100, 1) if usage.total else 0.0
        disks.append(
            DiskVolume(
                path=path,
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                percent_used=percent_used,
            )
        )

    if not disks:
        warnings.append(
            DiagnosticWarning(
                domain="storage",
                code="no-disk-data",
                message="No disk usage data could be collected.",
            )
        )
    if progress_callback is not None:
        progress_callback(1)

    device_health = _collect_storage_device_health()
    storage_devices = [
        StorageDeviceHealth(
            device_id=str(item["device_id"]),
            model=_coerce_string(item.get("model")),
            protocol=_coerce_string(item.get("protocol")),
            medium=_coerce_string(item.get("medium")),
            health_status=_coerce_string(item.get("health_status")),
            operational_status=_coerce_string(item.get("operational_status")),
        )
        for item in (device_health or [])
        if item.get("device_id") is not None
    ]
    if device_health is None and current_platform() in {"macos", "windows"}:
        warnings.append(
            DiagnosticWarning(
                domain="storage",
                code="storage-health-unavailable",
                message="Storage-device health could not be collected on this endpoint.",
            )
        )
    if progress_callback is not None:
        progress_callback(2)
    return disks, storage_devices, warnings


def _discover_mount_points() -> list[str]:
    platform_name = current_platform()
    if platform_name == "windows":
        return _windows_roots()

    result = run_command(["df", "-kP"])
    if result.succeeded:
        mount_points = []
        for line in result.stdout.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 6:
                mount_points.append(parts[-1])
        return _filter_mount_points(sorted(set(mount_points)), platform_name=platform_name)
    return ["/"]


def _filter_mount_points(mount_points: list[str], platform_name: str) -> list[str]:
    """Filter pseudo-filesystems that should not drive operator findings."""

    if platform_name != "macos":
        return mount_points

    filtered_mount_points: list[str] = []
    for path in mount_points:
        if path in _MACOS_IGNORED_MOUNT_POINTS or path.startswith(_MACOS_IGNORED_MOUNT_PREFIXES):
            LOGGER.debug("Skipping macOS pseudo filesystem from storage findings: path=%s", path)
            continue
        filtered_mount_points.append(path)
    return filtered_mount_points


def _windows_roots() -> list[str]:
    roots: list[str] = []
    for drive_letter in string.ascii_uppercase:
        root = f"{drive_letter}:\\"
        if os.path.exists(root):
            roots.append(root)
    return roots or ["C:\\"]


def _collect_storage_device_health() -> list[dict[str, object]] | None:
    platform_name = current_platform()
    if platform_name == "linux":
        return linux.read_storage_device_health()
    if platform_name == "macos":
        return macos.read_storage_device_health()
    if platform_name == "windows":
        return windows.read_storage_device_health()
    return None


def _coerce_string(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None
