"""Tests for platform-specific network helper command selection."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.platform import linux, macos
from occams_beard.utils.subprocess import CommandResult


class MacosNetworkHelperTests(unittest.TestCase):
    """Validate macOS network helper behavior."""

    @patch("occams_beard.platform.macos.run_command")
    def test_read_arp_neighbors_uses_numeric_output_to_avoid_dns_resolution(
        self,
        mock_run_command,
    ) -> None:
        mock_run_command.return_value = CommandResult(
            args=("arp", "-an"),
            returncode=0,
            stdout="? (192.168.1.1) at aa:bb:cc:dd:ee:ff on en0 ifscope [ethernet]\n",
            stderr="",
            duration_ms=4,
        )

        neighbors, result = macos.read_arp_neighbors()

        self.assertEqual(result.args, ("arp", "-an"))
        self.assertEqual(neighbors[0]["ip_address"], "192.168.1.1")
        mock_run_command.assert_called_once_with(["arp", "-an"], timeout=3.0)


class LinuxNetworkHelperTests(unittest.TestCase):
    """Validate Linux network helper fallback behavior."""

    @patch("occams_beard.platform.linux.run_command")
    def test_read_arp_neighbors_falls_back_to_numeric_arp_output_when_ip_neigh_fails(
        self,
        mock_run_command,
    ) -> None:
        mock_run_command.side_effect = [
            CommandResult(
                args=("ip", "neigh", "show"),
                returncode=None,
                stdout="",
                stderr="",
                duration_ms=5,
                error="command-not-found:ip",
            ),
            CommandResult(
                args=("arp", "-an"),
                returncode=0,
                stdout="? (192.168.1.1) at aa:bb:cc:dd:ee:ff on eth0\n",
                stderr="",
                duration_ms=3,
            ),
        ]

        neighbors, result = linux.read_arp_neighbors()

        self.assertEqual(result.args, ("arp", "-an"))
        self.assertEqual(neighbors[0]["interface"], "eth0")
        self.assertEqual(mock_run_command.call_args_list[1].args[0], ["arp", "-an"])
        self.assertEqual(mock_run_command.call_args_list[1].kwargs, {"timeout": 3.0})


if __name__ == "__main__":
    unittest.main()
