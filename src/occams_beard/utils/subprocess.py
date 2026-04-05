"""Small subprocess wrapper with timing and graceful failures."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from occams_beard.models import RawCommandCapture

LOGGER = logging.getLogger(__name__)
_COMMAND_CAPTURE_SINK: ContextVar[list[RawCommandCapture] | None] = ContextVar(
    "command_capture_sink",
    default=None,
)


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


@contextmanager
def capture_command_output() -> Iterator[list[RawCommandCapture]]:
    """Capture raw command execution output for the active context."""

    captured: list[RawCommandCapture] = []
    token = _COMMAND_CAPTURE_SINK.set(captured)
    try:
        yield captured
    finally:
        _COMMAND_CAPTURE_SINK.reset(token)


def run_command(
    args: list[str],
    timeout: float = 5.0,
    *,
    capture_output_for_bundle: bool = True,
) -> CommandResult:
    """Run a command without raising, capturing stdout and stderr."""

    start = time.perf_counter()
    if not args:
        raise ValueError("args must not be empty")

    if not command_available(args[0]):
        duration_ms = int((time.perf_counter() - start) * 1000)
        result = CommandResult(
            args=tuple(args),
            returncode=None,
            stdout="",
            stderr="",
            duration_ms=duration_ms,
            error=f"command-not-found:{args[0]}",
        )
        _record_capture(result, enabled=capture_output_for_bundle)
        return result

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
        result = CommandResult(
            args=tuple(args),
            returncode=None,
            stdout=_coerce_process_output(exc.stdout),
            stderr=_coerce_process_output(exc.stderr),
            duration_ms=duration_ms,
            timed_out=True,
            error="timeout",
        )
        _record_capture(result, enabled=capture_output_for_bundle)
        return result
    except OSError as exc:
        duration_ms = int((time.perf_counter() - start) * 1000)
        result = CommandResult(
            args=tuple(args),
            returncode=None,
            stdout="",
            stderr="",
            duration_ms=duration_ms,
            error=str(exc),
        )
        _record_capture(result, enabled=capture_output_for_bundle)
        return result

    duration_ms = int((time.perf_counter() - start) * 1000)
    result = CommandResult(
        args=tuple(args),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=duration_ms,
    )
    _record_capture(result, enabled=capture_output_for_bundle)
    return result


def _coerce_process_output(output: str | bytes | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return output


def _record_capture(result: CommandResult, *, enabled: bool) -> None:
    if not enabled:
        return
    captured = _COMMAND_CAPTURE_SINK.get()
    if captured is None:
        return
    captured.append(
        RawCommandCapture(
            command=list(result.args),
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_ms=result.duration_ms,
            timed_out=result.timed_out,
            error=result.error,
        )
    )
