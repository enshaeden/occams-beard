"""Small subprocess wrapper with timing and graceful failures."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class CommandResult:
    """Represents the result of a subprocess invocation."""

    args: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        """Return True when the command completed successfully."""

        return self.returncode == 0 and not self.timed_out and not self.error


def command_available(command: str) -> bool:
    """Return True when the command exists in PATH."""

    return shutil.which(command) is not None


def run_command(args: list[str], timeout: float = 5.0) -> CommandResult:
    """Run a command without raising, capturing stdout and stderr."""

    start = time.perf_counter()
    if not args:
        raise ValueError("args must not be empty")

    if not command_available(args[0]):
        duration_ms = int((time.perf_counter() - start) * 1000)
        return CommandResult(
            args=tuple(args),
            returncode=None,
            stdout="",
            stderr="",
            duration_ms=duration_ms,
            error=f"command-not-found:{args[0]}",
        )

    LOGGER.debug("Running command: %s", args)
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return CommandResult(
            args=tuple(args),
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            duration_ms=duration_ms,
            timed_out=True,
            error="timeout",
        )
    except OSError as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        return CommandResult(
            args=tuple(args),
            returncode=None,
            stdout="",
            stderr="",
            duration_ms=duration_ms,
            error=str(exc),
        )

    duration_ms = int((time.perf_counter() - start) * 1000)
    return CommandResult(
        args=tuple(args),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=duration_ms,
    )
