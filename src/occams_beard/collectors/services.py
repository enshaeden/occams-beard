"""Collectors for configured service and port checks."""

from __future__ import annotations

from collections.abc import Callable

from occams_beard.collectors.connectivity import check_tcp_target
from occams_beard.models import ServiceCheck, ServiceState, TcpTarget


def collect_service_state(
    targets: list[TcpTarget],
    *,
    progress_callback: Callable[[int], None] | None = None,
) -> ServiceState:
    """Run TCP service reachability checks for configured targets."""

    checks = []
    completed_steps = 0
    for target in targets:
        tcp_result = check_tcp_target(target)
        checks.append(
            ServiceCheck(
                target=target,
                success=tcp_result.success,
                latency_ms=tcp_result.latency_ms,
                error=tcp_result.error,
                duration_ms=tcp_result.duration_ms,
            )
        )
        completed_steps += 1
        if progress_callback is not None:
            progress_callback(completed_steps)
    return ServiceState(checks=checks)
