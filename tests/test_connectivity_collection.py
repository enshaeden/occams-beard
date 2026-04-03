"""Tests for connectivity collectors."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.collectors.connectivity import check_trace_target
from occams_beard.utils.subprocess import CommandResult


class ConnectivityCollectionTests(unittest.TestCase):
    """Validate traceroute collection behavior."""

    @patch("occams_beard.collectors.connectivity.current_platform", return_value="linux")
    @patch("occams_beard.collectors.connectivity.socket.gethostbyname", return_value="1.1.1.1")
    @patch("occams_beard.collectors.connectivity.run_command")
    def test_check_trace_target_marks_completed_trace_when_target_is_reached(
        self,
        mock_run_command,
        _mock_resolve,
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

        self.assertIsNone(warning)
        self.assertTrue(trace_result.ran)
        self.assertTrue(trace_result.success)
        self.assertFalse(trace_result.partial)
        self.assertEqual(trace_result.target_address, "1.1.1.1")
        self.assertEqual(trace_result.last_responding_hop, 2)

    @patch("occams_beard.collectors.connectivity.current_platform", return_value="linux")
    @patch("occams_beard.collectors.connectivity.socket.gethostbyname", return_value="140.82.114.3")
    @patch("occams_beard.collectors.connectivity.run_command")
    def test_check_trace_target_marks_partial_trace_when_target_not_reached(
        self,
        mock_run_command,
        _mock_resolve,
        _mock_platform,
    ) -> None:
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

        self.assertIsNone(warning)
        self.assertTrue(trace_result.ran)
        self.assertFalse(trace_result.success)
        self.assertTrue(trace_result.partial)
        self.assertEqual(trace_result.last_responding_hop, 2)
        self.assertIsNone(trace_result.error)

    @patch("occams_beard.collectors.connectivity.current_platform", return_value="linux")
    @patch("occams_beard.collectors.connectivity.socket.gethostbyname", side_effect=OSError("no-dns"))
    @patch("occams_beard.collectors.connectivity.run_command")
    def test_check_trace_target_warns_when_command_is_unavailable(
        self,
        mock_run_command,
        _mock_resolve,
        _mock_platform,
    ) -> None:
        mock_run_command.return_value = CommandResult(
            args=("traceroute", "-n", "-m", "5", "-w", "1", "github.com"),
            returncode=None,
            stdout="",
            stderr="",
            duration_ms=1,
            error="command-not-found:traceroute",
        )

        trace_result, warning = check_trace_target("github.com")

        self.assertIsNotNone(warning)
        self.assertFalse(trace_result.ran)
        self.assertEqual(trace_result.error, "trace-command-unavailable")
        self.assertIsNone(trace_result.target_address)


if __name__ == "__main__":
    unittest.main()
