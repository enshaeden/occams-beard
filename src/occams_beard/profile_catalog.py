"""Local diagnostics profile loading and validation."""

from __future__ import annotations

import importlib.resources
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from occams_beard.defaults import ALLOWED_CHECKS
from occams_beard.models import DiagnosticProfile, TcpTarget

LOCAL_PROFILE_DIR_NAME = "profiles"
ProfileSource = Literal["built_in", "local", "env"]


@dataclass(slots=True, frozen=True)
class ProfileCatalogIssue:
    """Non-fatal issue discovered while loading optional profile files."""

    source: ProfileSource
    path: str
    reason: str


@dataclass(slots=True, frozen=True)
class ProfileCatalog:
    """Combined view of valid profiles and any skipped optional files."""

    profiles: list[DiagnosticProfile]
    issues: list[ProfileCatalogIssue]


@dataclass(slots=True, frozen=True)
class _ProfileCandidate:
    source: ProfileSource
    path: Path


class ProfileValidationError(ValueError):
    """Structured validation failure for a single profile file."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{reason}: {path}")


def list_profiles() -> list[DiagnosticProfile]:
    """Return built-in and local profiles sorted by profile identifier."""

    return get_profile_catalog().profiles


def get_profile_catalog() -> ProfileCatalog:
    """Return the combined profile catalog and any skipped optional files."""

    profiles_by_id: dict[str, DiagnosticProfile] = {}
    issues: list[ProfileCatalogIssue] = []
    for candidate in _iter_profile_files():
        try:
            profile = _load_profile_file(candidate.path)
        except ProfileValidationError as exc:
            if candidate.source == "built_in":
                raise
            issues.append(
                ProfileCatalogIssue(
                    source=candidate.source,
                    path=str(exc.path),
                    reason=exc.reason,
                )
            )
            continue
        profiles_by_id[profile.profile_id] = profile
    return ProfileCatalog(
        profiles=[profiles_by_id[profile_id] for profile_id in sorted(profiles_by_id)],
        issues=issues,
    )


def get_profile(profile_id: str) -> DiagnosticProfile:
    """Return a single validated profile by identifier."""

    for profile in list_profiles():
        if profile.profile_id == profile_id:
            return profile
    raise ValueError(f"Unknown profile: {profile_id}")


def _iter_profile_files() -> list[_ProfileCandidate]:
    built_in_root = Path(str(importlib.resources.files("occams_beard.profiles")))
    candidates = [
        _ProfileCandidate(source="built_in", path=path)
        for path in sorted(built_in_root.glob("*.toml"))
    ]

    local_root = Path.cwd() / LOCAL_PROFILE_DIR_NAME
    if local_root.exists():
        candidates.extend(
            _ProfileCandidate(source="local", path=path)
            for path in sorted(local_root.glob("*.toml"))
        )

    env_override = os.environ.get("OCCAMS_BEARD_PROFILE_DIR")
    if env_override:
        override_root = Path(env_override)
        if override_root.exists():
            candidates.extend(
                _ProfileCandidate(source="env", path=path)
                for path in sorted(override_root.glob("*.toml"))
            )

    return candidates


def _load_profile_file(path: Path) -> DiagnosticProfile:
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProfileValidationError(path, "Profile file does not exist") from exc
    except OSError as exc:
        raise ProfileValidationError(path, "Profile file could not be read") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ProfileValidationError(path, "Profile file is not valid TOML") from exc

    profile_id = _require_non_empty_string(payload, "id", path)
    name = _require_non_empty_string(payload, "name", path)
    description = _require_non_empty_string(payload, "description", path)
    issue_category = _require_non_empty_string(payload, "issue_category", path)
    recommended_checks = _require_string_list(payload, "recommended_checks", path)
    invalid_checks = [check for check in recommended_checks if check not in ALLOWED_CHECKS]
    if invalid_checks:
        raise ProfileValidationError(
            path,
            "Profile "
            f"{profile_id} contains unsupported checks: {', '.join(sorted(set(invalid_checks)))}"
        )

    dns_hosts = _optional_string_list(payload, "dns_hosts", path)
    labels = _optional_string_list(payload, "labels", path)
    safe_user_guidance = _optional_string_list(payload, "safe_user_guidance", path)
    escalation_guidance = _optional_string_list(payload, "escalation_guidance", path)
    tcp_targets = _parse_tcp_targets(payload.get("tcp_targets"), path, profile_id)

    return DiagnosticProfile(
        profile_id=profile_id,
        name=name,
        description=description,
        issue_category=issue_category,
        recommended_checks=recommended_checks,
        dns_hosts=dns_hosts,
        tcp_targets=tcp_targets,
        labels=labels,
        safe_user_guidance=safe_user_guidance,
        escalation_guidance=escalation_guidance,
    )


def _parse_tcp_targets(
    payload: object,
    path: Path,
    profile_id: str,
) -> list[TcpTarget]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ProfileValidationError(path, f"Profile {profile_id} must use a list for tcp_targets")

    targets: list[TcpTarget] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ProfileValidationError(
                path,
                f"Profile {profile_id} entry tcp_targets[{index}] must be an object",
            )
        host = item.get("host")
        port = item.get("port")
        label = item.get("label")
        if not isinstance(host, str) or not host.strip():
            raise ProfileValidationError(
                path,
                f"Profile {profile_id} entry tcp_targets[{index}] has an invalid host",
            )
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ProfileValidationError(
                path,
                f"Profile {profile_id} entry tcp_targets[{index}] has an invalid port",
            )
        if label is not None and (not isinstance(label, str) or not label.strip()):
            raise ProfileValidationError(
                path,
                f"Profile {profile_id} entry tcp_targets[{index}] has an invalid label",
            )
        targets.append(
            TcpTarget(host=host.strip(), port=port, label=label.strip() if label else None)
        )
    return targets


def _require_non_empty_string(payload: dict[str, object], key: str, path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ProfileValidationError(path, f"Profile field {key!r} must be a non-empty string")
    return value.strip()


def _require_string_list(payload: dict[str, object], key: str, path: Path) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not value:
        raise ProfileValidationError(
            path,
            f"Profile field {key!r} must be a non-empty list of strings",
        )
    return _normalize_string_list(value, key, path)


def _optional_string_list(payload: dict[str, object], key: str, path: Path) -> list[str]:
    value = payload.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ProfileValidationError(path, f"Profile field {key!r} must be a list of strings")
    return _normalize_string_list(value, key, path)


def _normalize_string_list(raw_values: list[object], key: str, path: Path) -> list[str]:
    normalized: list[str] = []
    for index, item in enumerate(raw_values):
        if not isinstance(item, str) or not item.strip():
            raise ProfileValidationError(
                path,
                f"Profile field {key!r} entry {index} must be a non-empty string",
            )
        normalized.append(item.strip())
    return normalized
