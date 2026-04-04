"""Helpers for describing the active local runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from occams_beard import __version__
from occams_beard import platform as platform_package


def current_runtime_metadata() -> dict[str, object]:
    """Return a stable description of the active interpreter and package paths."""

    package_path = Path(__file__).resolve().parent
    return {
        "app_version": __version__,
        "pid": os.getpid(),
        "interpreter_path": str(Path(sys.executable).resolve()),
        "package_path": str(package_path),
        "windows_platform_module_path": str((package_path / "platform" / "windows.py").resolve()),
        "platform_package_path": str(Path(platform_package.__file__).resolve()),
    }


def runtime_fingerprint(metadata: dict[str, object] | None) -> tuple[object, object, object]:
    """Return a compact tuple suitable for comparing two runtimes."""

    if metadata is None:
        return (None, None, None)
    return (
        metadata.get("app_version"),
        metadata.get("interpreter_path"),
        metadata.get("package_path"),
    )
