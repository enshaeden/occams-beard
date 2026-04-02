"""Collectors for disk and filesystem usage."""

from __future__ import annotations

import os
import shutil
import string

from endpoint_diagnostics_lab.models import DiagnosticWarning, DiskVolume
from endpoint_diagnostics_lab.platform import current_platform
from endpoint_diagnostics_lab.utils.subprocess import run_command


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
        return sorted(set(mount_points))
    return ["/"]


def _windows_roots() -> list[str]:
    roots: list[str] = []
    for drive_letter in string.ascii_uppercase:
        root = f"{drive_letter}:\\"
        if os.path.exists(root):
            roots.append(root)
    return roots or ["C:\\"]
