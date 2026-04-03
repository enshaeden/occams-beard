"""Time-bounded hostname resolution helpers."""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Thread
from typing import Any, TypeVar

from occams_beard.utils.validation import dedupe_preserve_order

HOSTNAME_RESOLUTION_TIMEOUT_SECONDS = 2.0

_T = TypeVar("_T")


@dataclass(slots=True)
class HostnameResolutionResult:
    """Outcome of a time-bounded hostname resolution attempt."""

    addresses: list[str]
    error: str | None
    timed_out: bool
    duration_ms: int


def resolve_hostname_addresses(
    hostname: str,
    *,
    timeout: float = HOSTNAME_RESOLUTION_TIMEOUT_SECONDS,
) -> HostnameResolutionResult:
    """Resolve a hostname to one or more addresses without blocking indefinitely."""

    if _looks_like_ip_address(hostname):
        return HostnameResolutionResult(
            addresses=[hostname],
            error=None,
            timed_out=False,
            duration_ms=0,
        )

    timed_out, value, error, duration_ms = _run_with_timeout(
        lambda: socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP),
        timeout=timeout,
    )
    if timed_out:
        return HostnameResolutionResult(
            addresses=[],
            error="hostname-resolution-timeout",
            timed_out=True,
            duration_ms=duration_ms,
        )
    if error is not None:
        return HostnameResolutionResult(
            addresses=[],
            error=str(error),
            timed_out=False,
            duration_ms=duration_ms,
        )

    resolved_addresses: list[str] = []
    for _family, _socktype, _proto, _canonname, sockaddr in value or []:
        host = sockaddr[0]
        if isinstance(host, str):
            resolved_addresses.append(host)
    return HostnameResolutionResult(
        addresses=dedupe_preserve_order(resolved_addresses),
        error=None,
        timed_out=False,
        duration_ms=duration_ms,
    )


def _run_with_timeout(
    function: Callable[[], _T],
    *,
    timeout: float,
) -> tuple[bool, _T | None, BaseException | None, int]:
    state: dict[str, Any] = {}
    completed = Event()
    start = time.perf_counter()

    def _worker() -> None:
        try:
            state["value"] = function()
        except BaseException as exc:  # pragma: no cover - exercised through callers.
            state["error"] = exc
        finally:
            completed.set()

    Thread(target=_worker, daemon=True, name="occams-beard-resolve").start()
    if not completed.wait(timeout):
        return True, None, None, int((time.perf_counter() - start) * 1000)
    return (
        False,
        state.get("value"),
        state.get("error"),
        int((time.perf_counter() - start) * 1000),
    )


def _looks_like_ip_address(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True
