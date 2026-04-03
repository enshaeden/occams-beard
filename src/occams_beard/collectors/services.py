"""Collectors for configured service and port checks."""

from __future__ import annotations

from occams_beard.collectors.connectivity import check_tcp_target
from occams_beard.models import ServiceCheck, ServiceState, TcpTarget


def collect_service_state(targets: list[TcpTarget]) -> ServiceState:
    """Run TCP service reachability checks for configured targets."""

    checks = []
    for target in targets:
        tcp_result = check_tcp_target(target)
        checks.append(
            ServiceCheck(
                target=target,
                success=tcp_result.success,
                latency_ms=tcp_result.latency_ms,
                error=tcp_result.error,
            )
        )
    return ServiceState(checks=checks)
