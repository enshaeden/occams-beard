"""Bounded live smoke validation for supported local collectors."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from occams_beard.models import DomainExecution, EndpointDiagnosticResult, RawCommandCapture
from occams_beard.platform import current_platform
from occams_beard.runner import DiagnosticsRunOptions, run_diagnostics
from occams_beard.schema import RESULT_SCHEMA_VERSION

LIVE_SMOKE_CHECKS = ["host", "resources", "network", "routing", "dns"]
_ALLOWED_ROUTE_STATES = {"missing", "present", "suspect"}


class SmokeValidationError(RuntimeError):
    """Raised when a live smoke run does not meet the expected contract."""


def build_live_smoke_options() -> DiagnosticsRunOptions:
    """Return bounded options for local parser smoke validation."""

    return DiagnosticsRunOptions(
        selected_checks=list(LIVE_SMOKE_CHECKS),
        targets=[],
        dns_hosts=[],
        capture_raw_commands=True,
    )


def run_live_smoke() -> tuple[EndpointDiagnosticResult, dict[str, Any]]:
    """Run bounded diagnostics and validate the resulting structure."""

    result = run_diagnostics(build_live_smoke_options())
    return result, validate_live_result(result)


def validate_live_result(
    result: EndpointDiagnosticResult,
    *,
    platform_name: str | None = None,
) -> dict[str, Any]:
    """Validate a live diagnostics result and return a non-sensitive summary."""

    normalized_platform = platform_name or current_platform()
    if result.schema_version != RESULT_SCHEMA_VERSION:
        raise SmokeValidationError(
            f"Expected schema version {RESULT_SCHEMA_VERSION}, got {result.schema_version}."
        )
    if result.metadata.selected_checks != LIVE_SMOKE_CHECKS:
        raise SmokeValidationError(
            "Live smoke validation must run the bounded host/resources/network/routing/dns suite."
        )

    execution_by_domain = {record.domain: record for record in result.execution}
    for domain in LIVE_SMOKE_CHECKS:
        _require_selected_domain(domain, execution_by_domain)

    if not result.facts.network.interfaces:
        raise SmokeValidationError("No interfaces were collected from the live host.")
    if not result.facts.network.route_summary.routes:
        raise SmokeValidationError("No routes were collected from the live host.")
    if result.facts.network.route_summary.default_route_state not in _ALLOWED_ROUTE_STATES:
        raise SmokeValidationError(
            "Route summary returned an unexpected default route state: "
            f"{result.facts.network.route_summary.default_route_state}."
        )
    if not result.raw_command_capture:
        raise SmokeValidationError("Raw command capture was empty during live smoke validation.")

    _validate_platform_commands(normalized_platform, result.raw_command_capture)
    _validate_resolver_collection(result, normalized_platform)
    return build_live_smoke_summary(result, platform_name=normalized_platform)


def build_live_smoke_summary(
    result: EndpointDiagnosticResult,
    *,
    platform_name: str | None = None,
) -> dict[str, Any]:
    """Build a non-sensitive summary for CI artifacts and local review."""

    execution_statuses = {
        record.domain: record.status
        for record in result.execution
        if record.domain in LIVE_SMOKE_CHECKS
    }
    return {
        "platform": platform_name or current_platform(),
        "system": result.platform.system,
        "release": result.platform.release,
        "version": result.platform.version,
        "python_version": result.platform.python_version,
        "schema_version": result.schema_version,
        "selected_checks": list(result.metadata.selected_checks),
        "execution_statuses": execution_statuses,
        "interface_count": len(result.facts.network.interfaces),
        "active_interface_count": len(result.facts.network.active_interfaces),
        "route_count": len(result.facts.network.route_summary.routes),
        "resolver_count": len(result.facts.dns.resolvers),
        "default_route_state": result.facts.network.route_summary.default_route_state,
        "warnings": [asdict(warning) for warning in result.warnings],
        "captured_commands": [
            {
                "command": capture.command,
                "returncode": capture.returncode,
                "duration_ms": capture.duration_ms,
                "timed_out": capture.timed_out,
                "error": capture.error,
            }
            for capture in result.raw_command_capture
        ],
    }


def _require_selected_domain(
    domain: str, execution_by_domain: dict[str, DomainExecution]
) -> None:
    record = execution_by_domain.get(domain)
    if record is None:
        raise SmokeValidationError(f"Missing execution record for {domain}.")
    if not record.selected:
        raise SmokeValidationError(f"Execution record for {domain} was not marked selected.")
    if record.status in {"not_run", "skipped"}:
        raise SmokeValidationError(f"Execution record for {domain} did not actually run.")


def _validate_platform_commands(
    platform_name: str, captures: list[RawCommandCapture]
) -> None:
    if platform_name == "linux":
        _require_successful_prefix(
            captures,
            prefixes=(["ip", "addr", "show"], ["ifconfig"]),
            description="Linux interface inventory",
        )
        _require_successful_prefix(
            captures,
            prefixes=(["ip", "route", "show"], ["netstat", "-rn"]),
            description="Linux route inventory",
        )
        return

    if platform_name == "macos":
        _require_successful_prefix(
            captures,
            prefixes=(["ifconfig"],),
            description="macOS interface inventory",
        )
        _require_successful_prefix(
            captures,
            prefixes=(["netstat", "-rn"],),
            description="macOS route inventory",
        )
        if not any(
            _matches_prefix(capture, ["scutil", "--dns"])
            and (_capture_succeeded(capture) or _is_known_scutil_no_dns_capture(capture))
            for capture in captures
        ):
            raise SmokeValidationError(
                "macOS DNS resolver enumeration did not complete successfully. "
                "Expected scutil --dns."
            )
        return

    if platform_name == "windows":
        _require_successful_prefix(
            captures,
            prefixes=(["ipconfig", "/all"],),
            description="Windows interface inventory",
        )
        _require_successful_prefix(
            captures,
            prefixes=(["route", "print"],),
            description="Windows route inventory",
        )
        if not any(_is_successful_windows_dns_capture(capture) for capture in captures):
            raise SmokeValidationError("Windows DNS resolver enumeration did not run successfully.")
        return

    raise SmokeValidationError(f"Live smoke validation does not support platform {platform_name}.")


def _validate_resolver_collection(
    result: EndpointDiagnosticResult,
    platform_name: str,
) -> None:
    if result.facts.dns.resolvers:
        return
    if (
        platform_name == "macos"
        and _has_warning_code(result, "resolver-unavailable")
        and any(
            _is_known_scutil_no_dns_capture(capture) for capture in result.raw_command_capture
        )
    ):
        return
    raise SmokeValidationError("No resolvers were collected from the live host.")


def _require_successful_prefix(
    captures: list[RawCommandCapture],
    *,
    prefixes: tuple[list[str], ...],
    description: str,
) -> None:
    if any(
        _matches_prefix(capture, prefix) and _capture_succeeded(capture)
        for prefix in prefixes
        for capture in captures
    ):
        return
    joined_prefixes = ", ".join(" ".join(prefix) for prefix in prefixes)
    raise SmokeValidationError(
        f"{description} did not complete successfully. Expected {joined_prefixes}."
    )


def _matches_prefix(capture: RawCommandCapture, prefix: list[str]) -> bool:
    return capture.command[: len(prefix)] == prefix


def _capture_succeeded(capture: RawCommandCapture) -> bool:
    return capture.returncode == 0 and not capture.timed_out and capture.error is None


def _is_successful_windows_dns_capture(capture: RawCommandCapture) -> bool:
    if _matches_prefix(capture, ["powershell", "-NoProfile", "-Command"]):
        command_text = capture.command[-1] if capture.command else ""
        return "Get-DnsClientServerAddress" in command_text and _capture_succeeded(capture)
    return _matches_prefix(capture, ["ipconfig", "/all"]) and _capture_succeeded(capture)


def _is_known_scutil_no_dns_capture(capture: RawCommandCapture) -> bool:
    return (
        _matches_prefix(capture, ["scutil", "--dns"])
        and "No DNS configuration available" in capture.stdout
    )


def _has_warning_code(result: EndpointDiagnosticResult, code: str) -> bool:
    return any(warning.code == code for warning in result.warnings)
