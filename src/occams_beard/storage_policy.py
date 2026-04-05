"""Role-aware storage pressure policy helpers."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass

from occams_beard.models import DiskVolume

GiB = 1024**3
MiB = 1024**2

_ACTIONABLE_VOLUME_ROLES = frozenset({"system", "user_data", "other"})
_DIAGNOSTIC_VOLUME_ROLES = frozenset({"auxiliary", "ephemeral"})
_MACOS_PRIMARY_CAPACITY_PATHS = frozenset({"/", "/System/Volumes/Data"})


@dataclass(frozen=True, slots=True)
class DiskPressurePolicy:
    """Role-specific thresholds for operator-relevant storage pressure."""

    critical_free_ratio: float
    low_free_ratio: float
    low_free_bytes: int


_PRIMARY_PRESSURE_POLICY = DiskPressurePolicy(
    critical_free_ratio=0.05,
    low_free_ratio=0.10,
    low_free_bytes=15 * GiB,
)
_GENERAL_PRESSURE_POLICY = DiskPressurePolicy(
    critical_free_ratio=0.05,
    low_free_ratio=0.10,
    low_free_bytes=10 * GiB,
)
_AUXILIARY_PRESSURE_POLICY = DiskPressurePolicy(
    critical_free_ratio=0.02,
    low_free_ratio=0.05,
    low_free_bytes=1 * GiB,
)
_EPHEMERAL_PRESSURE_POLICY = DiskPressurePolicy(
    critical_free_ratio=0.01,
    low_free_ratio=0.03,
    low_free_bytes=512 * MiB,
)


def classify_volume_role(*, path: str, platform_name: str) -> str:
    """Return a coarse volume role for storage findings and explanations."""

    if platform_name == "windows":
        return "system" if path.upper() == "C:\\" else "other"

    normalized = path.rstrip("/") or "/"

    if platform_name == "macos":
        if normalized == "/":
            return "system"
        if normalized == "/System/Volumes/Data":
            return "user_data"
        if normalized.startswith("/System/Volumes/Data/"):
            return "ephemeral"
        if normalized.startswith("/System/Volumes/"):
            return "auxiliary"
        if normalized in {"/Users", "/home"}:
            return "user_data"
        return "other"

    if normalized in {"/", "/var", "/tmp", "/usr", "/opt"}:
        return "system"
    if normalized in {"/home", "/Users"}:
        return "user_data"
    return "other"


def classify_disk_pressure(
    *,
    total_bytes: int,
    free_bytes: int,
    role_hint: str | None,
) -> str:
    """Classify current storage pressure using role-aware thresholds."""

    if total_bytes <= 0:
        return "unknown"

    free_ratio = free_bytes / total_bytes
    policy = _disk_pressure_policy(role_hint=role_hint)

    if free_ratio <= policy.critical_free_ratio:
        return "critical"
    if free_ratio <= policy.low_free_ratio and free_bytes <= policy.low_free_bytes:
        return "low"
    return "normal"


def is_actionable_volume_role(role_hint: str | None) -> bool:
    """Return whether a volume should drive default operator findings."""

    if role_hint is None:
        return True
    return role_hint in _ACTIONABLE_VOLUME_ROLES


def is_diagnostic_only_volume_role(role_hint: str | None) -> bool:
    """Return whether a volume is diagnostic context instead of an incident target."""

    return role_hint in _DIAGNOSTIC_VOLUME_ROLES


def disk_has_capacity_data(disk: DiskVolume) -> bool:
    """Return whether the mount exposes usable capacity metrics."""

    return disk.total_bytes > 0 and disk.free_percent is not None


def is_zero_capacity_pseudo_mount(disk: DiskVolume) -> bool:
    """Return whether the mount is diagnostic-only for capacity reasoning."""

    return not disk_has_capacity_data(disk)


def distinct_capacity_groups(
    disks: Iterable[DiskVolume],
    *,
    actionable_only: bool = False,
) -> list[list[DiskVolume]]:
    """Group mounts that should count as one underlying capacity condition."""

    groups: OrderedDict[tuple[object, ...], list[DiskVolume]] = OrderedDict()
    for disk in disks:
        if not disk_has_capacity_data(disk):
            continue
        if actionable_only and not is_actionable_volume_role(disk.role_hint):
            continue
        key = _capacity_group_key(disk)
        groups.setdefault(key, []).append(disk)
    return list(groups.values())


def capacity_group_label(group: list[DiskVolume]) -> str:
    """Render a stable operator-facing label for a grouped capacity pool."""

    paths = sorted({disk.path for disk in group}, key=_path_preference_key)
    if len(paths) == 2 and set(paths) == _MACOS_PRIMARY_CAPACITY_PATHS:
        return "/ and /System/Volumes/Data"
    return ", ".join(paths)


def capacity_group_representative(group: list[DiskVolume]) -> DiskVolume:
    """Pick the most actionable representative for a grouped capacity pool."""

    return min(
        group,
        key=lambda disk: (
            _role_preference(disk.role_hint),
            _path_preference_key(disk.path),
        ),
    )


def _disk_pressure_policy(*, role_hint: str | None) -> DiskPressurePolicy:
    if role_hint in {"system", "user_data"}:
        return _PRIMARY_PRESSURE_POLICY
    if role_hint == "auxiliary":
        return _AUXILIARY_PRESSURE_POLICY
    if role_hint == "ephemeral":
        return _EPHEMERAL_PRESSURE_POLICY
    return _GENERAL_PRESSURE_POLICY


def _capacity_group_key(disk: DiskVolume) -> tuple[object, ...]:
    normalized = disk.path.rstrip("/") or "/"
    if normalized in _MACOS_PRIMARY_CAPACITY_PATHS and disk.role_hint in {"system", "user_data"}:
        return (
            "macos-primary-container",
            disk.total_bytes,
            disk.used_bytes,
            disk.free_bytes,
        )
    return ("mount", normalized)


def _role_preference(role_hint: str | None) -> int:
    return {
        "user_data": 0,
        "system": 1,
        "other": 2,
        "auxiliary": 3,
        "ephemeral": 4,
        None: 5,
    }.get(role_hint, 5)


def _path_preference_key(path: str) -> tuple[int, str]:
    return (
        {
            "/System/Volumes/Data": 0,
            "/": 1,
        }.get(path.rstrip("/") or "/", 10),
        path,
    )
