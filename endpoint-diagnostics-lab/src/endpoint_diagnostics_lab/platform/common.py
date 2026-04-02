"""Common platform helpers."""

from __future__ import annotations

import platform as python_platform


def current_platform() -> str:
    """Return the normalized current platform name."""

    system = python_platform.system().lower()
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if system == "linux":
        return "linux"
    return system
