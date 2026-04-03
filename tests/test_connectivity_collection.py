"""Tests for connectivity collectors."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.collectors.connectivity import check_trace_target, collect_connectivity_state
from occams_beard.models import PingResult, TcpConnectivityCheck, TcpTarget, TraceResult
from occams_beard.utils.resolution import HostnameResolutionResult
from occams_beard.utils.subprocess import CommandResult


class ConnectivityCollectionTests(unittest.TestCase):
    """Validate traceroute collection behavior."""

    @patch("occams_beard.collectors.connectivity.check_trace_target")
    @patch("occams_beard.collectors.connectivity.check_ping_target")
    @patch("occams_beard.collectors.connectivity.check_tcp_target")
    def test_collect_connectivity_state_reports_incremental_progress_for_multi_target_run(
        self,
        mock_check_tcp_target,
        mock_check_ping_target,
        mock_check_trace_target,
    ) -> None:
        mock_check_tcp_target.side_effect = [
            TcpConnectivityCheck(
                target=TcpTarget(host="github.com", port=443),
                success=True,
                latency_ms=21.2,
                duration_ms=21,
            ),
            TcpConnectivityCheck(
                target=TcpTarget(host="1.1.1.1", port=53),
                success=False,
                error="timeout",
                duration_ms=30,
            ),
        ]
        mock_check_ping_target.side_effect = [
            (
                PingResult(target="github.com", success=True, duration_ms=12),
                None,
            ),
            (
                PingResult(target="1.1.1.1", success=False, error="ping-failed", duration_ms=18),
                None,
            ),
        ]
        mock_check_trace_target.side_effect = [
            (
                TraceResult(target="github.com", ran=True, success=True, duration_ms=40),
                [],
            ),
            (
                TraceResult(
                    target="1.1.1.1",
                    ran=True,
                    success=False,
                    partial=True,
                    duration_ms=55,
                ),
                [],
            ),
        ]
        progress_updates: list[int] = []

        state, warnings = collect_connectivity_state(
            [
                TcpTarget(host="github.com", port=443),
                TcpTarget(host="1.1.1.1", port=53),
            ],
            enable_ping=True,
            enable_trace=True,
            progress_callback=progress_updates.append,
        )

        self.assertEqual(progress_updates, [1, 2, 3, 4, 5, 6])
        self.assertEqual(len(state.tcp_checks), 2)
        self.assertEqual(len(state.ping_checks), 2)
        self.assertEqual(len(state.trace_results), 2)
        self.assertEqual(warnings, [])

    @patch("occams_beard.collectors.connectivity.current_platform", return_value="linux")
    @patch("occams_beard.collectors.connectivity.run_command")
    def test_check_trace_target_marks_completed_trace_when_target_is_reached(
        self,
        mock_run_command,
        _mock_platform,
    ) -> None:
        mock_run_command.return_value = CommandResult(
            args=("traceroute", "-n", "-m", "5", "-w", "1", "1.1.1.1"),
            returncode=0,
            stdout=(
                "traceroute to 1.1.1.1 (1.1.1.1), 5 hops max, 60 byte packets\n"
                " 1  192.168.1.1  1.123 ms\n"
                " 2  1.1.1.1  10.321 ms\n"
            ),
            stderr="",
            duration_ms=10,
        )

        trace_result, warning = check_trace_target("1.1.1.1")

        self.assertEqual(warning, [])
        self.assertTrue(trace_result.ran)
        self.assertTrue(trace_result.success)
        self.assertFalse(trace_result.partial)
        self.assertEqual(trace_result.target_address, "1.1.1.1")
        self.assertEqual(trace_result.last_responding_hop, 2)

    @patch("occams_beard.collectors.connectivity.current_platform", return_value="linux")
    @patch("occams_beard.collectors.connectivity.resolve_hostname_addresses")
    @patch("occams_beard.collectors.connectivity.run_command")
    def test_check_trace_target_marks_partial_trace_when_target_not_reached(
        self,
        mock_run_command,
        mock_resolve,
        _mock_platform,
    ) -> None:
        mock_resolve.return_value = HostnameResolutionResult(
            addresses=["140.82.114.3"],
            error=None,
            timed_out=False,
            duration_ms=12,
        )
        mock_run_command.return_value = CommandResult(
            args=("traceroute", "-n", "-m", "5", "-w", "1", "github.com"),
            returncode=0,
            stdout=(
                "traceroute to github.com (140.82.114.3), 5 hops max, 60 byte packets\n"
                " 1  192.168.1.1  1.123 ms\n"
                " 2  10.0.0.1  9.112 ms\n"
                " 3  * * *\n"
            ),
            stderr="",
            duration_ms=10,
        )

        trace_result, warning = check_trace_target("github.com")

        self.assertEqual(warning, [])
        self.assertTrue(trace_result.ran)
        self.assertFalse(trace_result.success)
        self.assertTrue(trace_result.partial)
        self.assertEqual(trace_result.last_responding_hop, 2)
        self.assertIsNone(trace_result.error)

    @patch("occams_beard.collectors.connectivity.current_platform", return_value="linux")
    @patch("occams_beard.collectors.connectivity.resolve_hostname_addresses")
    @patch("occams_beard.collectors.connectivity.run_command")
    def test_check_trace_target_warns_when_command_is_unavailable(
        self,
        mock_run_command,
        mock_resolve,
        _mock_platform,
    ) -> None:
        mock_resolve.return_value = HostnameResolutionResult(
            addresses=[],
            error="no-dns",
            timed_out=False,
            duration_ms=10,
        )
        mock_run_command.return_value = CommandResult(
            args=("traceroute", "-n", "-m", "5", "-w", "1", "github.com"),
            returncode=None,
            stdout="",
            stderr="",
            duration_ms=1,
            error="command-not-found:traceroute",
        )

        trace_result, warning = check_trace_target("github.com")

        self.assertEqual([item.code for item in warning], ["trace-unavailable"])
        self.assertFalse(trace_result.ran)
        self.assertEqual(trace_result.error, "trace-command-unavailable")
        self.assertIsNone(trace_result.target_address)

    @patch("occams_beard.collectors.connectivity.current_platform", return_value="linux")
    @patch("occams_beard.collectors.connectivity.resolve_hostname_addresses")
    @patch("occams_beard.collectors.connectivity.run_command")
    def test_check_trace_target_warns_when_target_resolution_times_out(
        self,
        mock_run_command,
        mock_resolve,
        _mock_platform,
    ) -> None:
        mock_resolve.return_value = HostnameResolutionResult(
            addresses=[],
            error="hostname-resolution-timeout",
            timed_out=True,
            duration_ms=2000,
        )
        mock_run_command.return_value = CommandResult(
            args=("traceroute", "-n", "-m", "5", "-w", "1", "github.com"),
            returncode=0,
            stdout=(
                "traceroute to github.com (140.82.114.3), 5 hops max, 60 byte packets\n"
                " 1  192.168.1.1  1.123 ms\n"
                " 2  10.0.0.1  9.112 ms\n"
            ),
            stderr="",
            duration_ms=10,
        )

        trace_result, warnings = check_trace_target("github.com")

        self.assertTrue(trace_result.ran)
        self.assertFalse(trace_result.success)
        self.assertTrue(trace_result.partial)
        self.assertIsNone(trace_result.target_address)
        self.assertEqual(
            [warning.code for warning in warnings],
            ["trace-target-resolution-timeout"],
        )


if __name__ == "__main__":
    unittest.main()
