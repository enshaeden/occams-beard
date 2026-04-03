"""Tests for normalized network collection behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from endpoint_diagnostics_lab.collectors.network import collect_network_state
from endpoint_diagnostics_lab.utils.subprocess import CommandResult


class NetworkCollectionTests(unittest.TestCase):
    """Validate interface normalization and warning behavior."""

    @patch("endpoint_diagnostics_lab.collectors.network.current_platform", return_value="linux")
    @patch("endpoint_diagnostics_lab.collectors.network.linux.read_arp_neighbors")
    @patch("endpoint_diagnostics_lab.collectors.network.linux.read_interfaces")
    def test_collect_network_state_normalizes_active_interfaces(
        self,
        mock_read_interfaces,
        mock_read_arp_neighbors,
        _mock_platform,
    ) -> None:
        mock_read_interfaces.return_value = (
            [
                {
                    "name": "eth0",
                    "is_up": True,
                    "mac_address": "aa:bb:cc:dd:ee:ff",
                    "mtu": 1500,
                    "addresses": [
                        {
                            "family": "ipv4",
                            "address": "192.168.1.50",
                            "netmask": "24",
                            "is_loopback": False,
                        }
                    ],
                },
                {
                    "name": "utun2",
                    "is_up": True,
                    "mac_address": None,
                    "mtu": 1380,
                    "addresses": [],
                },
            ],
            CommandResult(
                args=("ip", "addr", "show"),
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=5,
            ),
        )
        mock_read_arp_neighbors.return_value = (
            [
                {
                    "ip_address": "192.168.1.1",
                    "mac_address": "aa:bb:cc:dd:ee:ff",
                    "interface": "eth0",
                    "state": "reachable",
                }
            ],
            CommandResult(
                args=("ip", "neigh", "show"),
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=5,
            ),
        )

        network_state, warnings = collect_network_state()

        self.assertEqual(network_state.active_interfaces, ["eth0", "utun2"])
        self.assertEqual(network_state.local_addresses, ["192.168.1.50"])
        self.assertEqual(network_state.interfaces[1].type_hint, "tunnel")
        self.assertEqual(network_state.arp_neighbors[0].ip_address, "192.168.1.1")
        self.assertEqual(warnings, [])

    @patch("endpoint_diagnostics_lab.collectors.network.current_platform", return_value="linux")
    @patch("endpoint_diagnostics_lab.collectors.network.linux.read_arp_neighbors")
    @patch("endpoint_diagnostics_lab.collectors.network.linux.read_interfaces")
    def test_collect_network_state_uses_more_conservative_interface_type_inference(
        self,
        mock_read_interfaces,
        mock_read_arp_neighbors,
        _mock_platform,
    ) -> None:
        mock_read_interfaces.return_value = (
            [
                {
                    "name": "Wi-Fi",
                    "is_up": True,
                    "mac_address": "aa:bb:cc:dd:ee:ff",
                    "mtu": 1500,
                    "addresses": [],
                },
                {
                    "name": "lan0",
                    "is_up": True,
                    "mac_address": "aa:bb:cc:dd:ee:11",
                    "mtu": 1500,
                    "addresses": [],
                },
                {
                    "name": "bridge100",
                    "is_up": True,
                    "mac_address": None,
                    "mtu": 1500,
                    "addresses": [],
                },
            ],
            CommandResult(
                args=("ip", "addr", "show"),
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=5,
            ),
        )
        mock_read_arp_neighbors.return_value = (
            [],
            CommandResult(
                args=("ip", "neigh", "show"),
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=5,
            ),
        )

        network_state, warnings = collect_network_state()

        self.assertEqual(network_state.interfaces[0].type_hint, "wireless")
        self.assertEqual(network_state.interfaces[1].type_hint, "ethernet")
        self.assertEqual(network_state.interfaces[2].type_hint, "unknown")
        self.assertEqual(warnings, [])

    @patch("endpoint_diagnostics_lab.collectors.network.current_platform", return_value="linux")
    @patch("endpoint_diagnostics_lab.collectors.network.linux.read_arp_neighbors")
    @patch("endpoint_diagnostics_lab.collectors.network.linux.read_interfaces")
    def test_collect_network_state_logs_warning_when_command_fails(
        self,
        mock_read_interfaces,
        mock_read_arp_neighbors,
        _mock_platform,
    ) -> None:
        mock_read_interfaces.return_value = (
            [],
            CommandResult(
                args=("ip", "addr", "show"),
                returncode=None,
                stdout="",
                stderr="missing",
                duration_ms=5,
                error="command-not-found:ip",
            ),
        )
        mock_read_arp_neighbors.return_value = (
            [],
            CommandResult(
                args=("ip", "neigh", "show"),
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=5,
            ),
        )

        network_state, warnings = collect_network_state()

        self.assertEqual(network_state.interfaces, [])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].code, "interface-command-failed")

    @patch("endpoint_diagnostics_lab.collectors.network.current_platform", return_value="linux")
    @patch("endpoint_diagnostics_lab.collectors.network.linux.read_arp_neighbors")
    @patch("endpoint_diagnostics_lab.collectors.network.linux.read_interfaces")
    def test_collect_network_state_logs_supplemental_warning_when_arp_collection_fails(
        self,
        mock_read_interfaces,
        mock_read_arp_neighbors,
        _mock_platform,
    ) -> None:
        mock_read_interfaces.return_value = (
            [],
            CommandResult(
                args=("ip", "addr", "show"),
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=5,
            ),
        )
        mock_read_arp_neighbors.return_value = (
            [],
            CommandResult(
                args=("arp", "-a"),
                returncode=None,
                stdout="",
                stderr="",
                duration_ms=5,
                error="command-not-found:arp",
            ),
        )

        _network_state, warnings = collect_network_state()

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].code, "arp-command-failed")


if __name__ == "__main__":
    unittest.main()
