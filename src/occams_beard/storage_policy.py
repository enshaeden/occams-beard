"""Role-aware storage pressure policy helpers."""

from __future__ import annotations

from dataclasses import dataclass

GiB = 1024**3
MiB = 1024**2

_ACTIONABLE_VOLUME_ROLES = frozenset({"system", "user_data", "other"})
_DIAGNOSTIC_VOLUME_ROLES = frozenset({"auxiliary", "ephemeral"})


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


def _disk_pressure_policy(*, role_hint: str | None) -> DiskPressurePolicy:
    if role_hint in {"system", "user_data"}:
        return _PRIMARY_PRESSURE_POLICY
    if role_hint == "auxiliary":
        return _AUXILIARY_PRESSURE_POLICY
    if role_hint == "ephemeral":
        return _EPHEMERAL_PRESSURE_POLICY
    return _GENERAL_PRESSURE_POLICY
