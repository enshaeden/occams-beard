"""Collectors for disk and filesystem usage."""

from __future__ import annotations

import logging
import os
import shutil
import string

from occams_beard.models import DiagnosticWarning, DiskVolume
from occams_beard.platform import current_platform
from occams_beard.utils.subprocess import run_command


LOGGER = logging.getLogger(__name__)

_MACOS_IGNORED_MOUNT_POINTS = frozenset(
    {
        "/dev",
    }
)
_MACOS_IGNORED_MOUNT_PREFIXES = (
    "/Library/Developer/CoreSimulator/Volumes/",
)


def collect_storage_state() -> tuple[list[DiskVolume], list[DiagnosticWarning]]:
    """Collect relevant volume or filesystem usage information."""

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
    return disks, warnings


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
                mount_points.append(parts[5])
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
