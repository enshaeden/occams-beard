"""Tests for bounded live smoke validation helpers."""

from __future__ import annotations

import unittest

from occams_beard.execution import build_execution_records
from occams_beard.live_smoke import (
    LIVE_SMOKE_CHECKS,
    SmokeValidationError,
    build_live_smoke_options,
    validate_live_result,
)
from occams_beard.models import DiagnosticWarning, RawCommandCapture, RouteEntry
from occams_beard.runner import DiagnosticsRunOptions
from support import build_sample_result


class LiveSmokeValidationTests(unittest.TestCase):
    """Validate live smoke guardrails without running live commands in unit tests."""

    def test_build_live_smoke_options_uses_bounded_local_checks(self) -> None:
        options = build_live_smoke_options()

        self.assertEqual(options.selected_checks, LIVE_SMOKE_CHECKS)
        self.assertEqual(options.targets, [])
        self.assertEqual(options.dns_hosts, [])
        self.assertTrue(options.capture_raw_commands)

    def test_validate_live_result_accepts_linux_summary_with_successful_capture(self) -> None:
        result = _build_live_smoke_result()
        result.raw_command_capture = [
            RawCommandCapture(
                command=["ip", "addr", "show"],
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=4,
            ),
            RawCommandCapture(
                command=["ip", "route", "show"],
                returncode=0,
                stdout="default via 192.168.1.1 dev eth0\n",
                stderr="",
                duration_ms=3,
            ),
        ]

        summary = validate_live_result(result, platform_name="linux")

        self.assertEqual(summary["platform"], "linux")
        self.assertEqual(summary["route_count"], 1)
        self.assertEqual(summary["resolver_count"], 1)

    def test_validate_live_result_rejects_windows_run_without_route_capture(self) -> None:
        result = _build_live_smoke_result()
        result.raw_command_capture = [
            RawCommandCapture(
                command=["ipconfig", "/all"],
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=4,
            ),
            RawCommandCapture(
                command=[
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-DnsClientServerAddress | Select-Object -ExpandProperty ServerAddresses",
                ],
                returncode=0,
                stdout="10.0.0.2\n",
                stderr="",
                duration_ms=5,
            ),
        ]

        with self.assertRaises(SmokeValidationError):
            validate_live_result(result, platform_name="windows")

    def test_validate_live_result_accepts_windows_ipconfig_dns_fallback(self) -> None:
        result = _build_live_smoke_result()
        result.facts.dns.resolvers = ["10.0.0.2"]
        result.raw_command_capture = [
            RawCommandCapture(
                command=["ipconfig", "/all"],
                returncode=0,
                stdout="DNS Servers . . . . . . . . . . . : 10.0.0.2\n",
                stderr="",
                duration_ms=4,
            ),
            RawCommandCapture(
                command=["route", "print"],
                returncode=0,
                stdout="0.0.0.0          0.0.0.0       10.0.0.1    10.0.0.50     25\n",
                stderr="",
                duration_ms=5,
            ),
        ]

        summary = validate_live_result(result, platform_name="windows")

        self.assertEqual(summary["platform"], "windows")
        self.assertEqual(summary["resolver_count"], 1)

    def test_validate_live_result_allows_explicit_macos_no_dns_configuration(self) -> None:
        result = _build_live_smoke_result()
        result.facts.dns.resolvers = []
        result.warnings.append(
            DiagnosticWarning(
                domain="dns",
                code="resolver-unavailable",
                message="Configured resolvers could not be determined on this endpoint.",
            )
        )
        result.raw_command_capture = [
            RawCommandCapture(
                command=["ifconfig"],
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=4,
            ),
            RawCommandCapture(
                command=["route", "-n", "get", "default"],
                returncode=0,
                stdout="gateway: 192.168.1.1\ninterface: en0\n",
                stderr="",
                duration_ms=2,
            ),
            RawCommandCapture(
                command=["netstat", "-rn"],
                returncode=0,
                stdout="default 192.168.1.1 UGSc en0\n",
                stderr="",
                duration_ms=3,
            ),
            RawCommandCapture(
                command=["scutil", "--dns"],
                returncode=1,
                stdout="No DNS configuration available\n",
                stderr="",
                duration_ms=3,
            ),
        ]

        summary = validate_live_result(result, platform_name="macos")

        self.assertEqual(summary["platform"], "macos")
        self.assertEqual(summary["resolver_count"], 0)


def _build_live_smoke_result():
    result = build_sample_result()
    result.metadata.selected_checks = list(LIVE_SMOKE_CHECKS)
    result.facts.network.route_summary.routes = [
        RouteEntry(
            destination="default",
            gateway="192.168.1.1",
            interface="eth0",
            metric=100,
        )
    ]
    options = DiagnosticsRunOptions(
        selected_checks=list(LIVE_SMOKE_CHECKS),
        targets=[],
        dns_hosts=[],
        capture_raw_commands=True,
    )
    result.execution = build_execution_records(
        result.facts,
        options,
        result.warnings,
        {"host": 1, "resources": 1, "network": 1, "routing": 1, "dns": 1},
    )
    return result


if __name__ == "__main__":
    unittest.main()
