"""Validated operator-facing options for a diagnostics run."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from occams_beard.defaults import (
    ALLOWED_CHECKS,
    DEFAULT_CHECKS,
    DEFAULT_DNS_HOSTS,
    DEFAULT_TCP_TARGETS,
    DEFAULT_TIME_REFERENCE_LABEL,
    DEFAULT_TIME_REFERENCE_URL,
)
from occams_beard.models import DiagnosticProfile, TcpTarget
from occams_beard.profile_catalog import get_profile
from occams_beard.utils.validation import (
    parse_check_selection,
    resolve_dns_hosts,
    resolve_tcp_targets,
)


@dataclass(slots=True)
class DiagnosticsRunOptions:
    """Validated operator-selected options for a diagnostics run."""

    selected_checks: list[str]
    targets: list[TcpTarget]
    dns_hosts: list[str]
    profile: DiagnosticProfile | None = None
    enable_ping: bool = False
    enable_trace: bool = False
    enable_time_skew_check: bool = False
    time_reference_label: str = DEFAULT_TIME_REFERENCE_LABEL
    time_reference_url: str = DEFAULT_TIME_REFERENCE_URL
    capture_raw_commands: bool = False


def build_run_options(
    *,
    checks: str | None = None,
    targets: Iterable[str] | None = None,
    target_file: str | None = None,
    dns_hosts: Iterable[str] | None = None,
    profile_id: str | None = None,
    enable_ping: bool = False,
    enable_trace: bool = False,
    enable_time_skew_check: bool = False,
    capture_raw_commands: bool = False,
) -> DiagnosticsRunOptions:
    """Build validated run options from operator-facing input values."""

    profile = get_profile(profile_id) if profile_id else None
    default_checks = profile.recommended_checks if profile is not None else DEFAULT_CHECKS
    default_targets = (
        profile.tcp_targets if profile is not None and profile.tcp_targets else DEFAULT_TCP_TARGETS
    )
    default_dns_hosts = (
        profile.dns_hosts if profile is not None and profile.dns_hosts else DEFAULT_DNS_HOSTS
    )

    return DiagnosticsRunOptions(
        selected_checks=parse_check_selection(
            checks,
            allowed_checks=ALLOWED_CHECKS,
            default_checks=default_checks,
        ),
        targets=resolve_tcp_targets(
            list(targets or []),
            target_file,
            default_targets=default_targets,
        ),
        dns_hosts=resolve_dns_hosts(list(dns_hosts or []), default_hosts=default_dns_hosts),
        profile=profile,
        enable_ping=enable_ping,
        enable_trace=enable_trace,
        enable_time_skew_check=enable_time_skew_check,
        capture_raw_commands=capture_raw_commands,
    )
