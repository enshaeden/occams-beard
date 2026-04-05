"""Tests for VPN and tunnel signal normalization."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.collectors.vpn import collect_vpn_state
from occams_beard.models import (
    InterfaceAddress,
    NetworkInterface,
    NetworkState,
    RouteEntry,
    RouteSummary,
)


class VpnCollectionTests(unittest.TestCase):
    """Validate conservative tunnel and VPN signal detection."""

    @patch("occams_beard.collectors.vpn.current_platform", return_value="linux")
    def test_collect_vpn_state_detects_active_tunnel_interface_without_assuming_default_route(
        self,
        _mock_platform,
    ) -> None:
        vpn_state = collect_vpn_state(
            NetworkState(
                interfaces=[
                    NetworkInterface(
                        name="wg0",
                        is_up=True,
                        addresses=[
                            InterfaceAddress(
                                family="ipv4",
                                address="10.20.0.10",
                                netmask="24",
                            )
                        ],
                        type_hint="tunnel",
                    ),
                    NetworkInterface(
                        name="eth0",
                        is_up=True,
                        addresses=[
                            InterfaceAddress(
                                family="ipv4",
                                address="192.168.1.50",
                                netmask="24",
                            )
                        ],
                        type_hint="ethernet",
                    ),
                ]
            ),
            RouteSummary(
                default_gateway="192.168.1.1",
                default_interface="eth0",
                has_default_route=True,
                routes=[
                    RouteEntry(
                        destination="default",
                        gateway="192.168.1.1",
                        interface="eth0",
                    )
                ],
                default_route_state="present",
            ),
        )

        self.assertEqual(len(vpn_state.signals), 1)
        self.assertEqual(vpn_state.signals[0].interface_name, "wg0")
        self.assertEqual(vpn_state.signals[0].signal_type, "interface-name-and-address-heuristic")

    @patch("occams_beard.collectors.vpn.current_platform", return_value="macos")
    def test_collect_vpn_state_adds_default_route_signal_for_tunnel_default_path(
        self,
        _mock_platform,
    ) -> None:
        vpn_state = collect_vpn_state(
            NetworkState(
                interfaces=[
                    NetworkInterface(
                        name="utun2",
                        is_up=True,
                        addresses=[
                            InterfaceAddress(
                                family="ipv4",
                                address="10.8.0.10",
                                netmask="24",
                            )
                        ],
                        type_hint="tunnel",
                    )
                ]
            ),
            RouteSummary(
                default_gateway="10.8.0.1",
                default_interface="utun2",
                has_default_route=True,
                routes=[
                    RouteEntry(
                        destination="default",
                        gateway="10.8.0.1",
                        interface="utun2",
                    )
                ],
                default_route_state="present",
            ),
        )

        self.assertEqual(len(vpn_state.signals), 1)
        self.assertEqual(vpn_state.signals[0].signal_type, "default-route-tunnel-heuristic")

    @patch("occams_beard.collectors.vpn.current_platform", return_value="macos")
    def test_collect_vpn_state_downgrades_ambiguous_macos_utun_inventory(
        self,
        _mock_platform,
    ) -> None:
        vpn_state = collect_vpn_state(
            NetworkState(
                interfaces=[
                    NetworkInterface(
                        name="utun2",
                        is_up=True,
                        addresses=[
                            InterfaceAddress(
                                family="ipv6",
                                address="fe80::1234%utun2",
                            )
                        ],
                        type_hint="tunnel",
                    ),
                    NetworkInterface(
                        name="utun3",
                        is_up=True,
                        addresses=[],
                        type_hint="tunnel",
                    ),
                    NetworkInterface(
                        name="en0",
                        is_up=True,
                        addresses=[
                            InterfaceAddress(
                                family="ipv4",
                                address="192.168.1.50",
                                netmask="24",
                            )
                        ],
                        type_hint="ethernet",
                    ),
                ]
            ),
            RouteSummary(
                default_gateway="192.168.1.1",
                default_interface="en0",
                has_default_route=True,
                routes=[
                    RouteEntry(
                        destination="default",
                        gateway="192.168.1.1",
                        interface="en0",
                    )
                ],
                default_route_state="present",
            ),
        )

        self.assertEqual(vpn_state.signals, [])

    @patch("occams_beard.collectors.vpn.current_platform", return_value="macos")
    def test_collect_vpn_state_marks_route_owned_utun_as_likely_vpn(
        self,
        _mock_platform,
    ) -> None:
        vpn_state = collect_vpn_state(
            NetworkState(
                interfaces=[
                    NetworkInterface(
                        name="utun3",
                        is_up=True,
                        addresses=[
                            InterfaceAddress(
                                family="ipv4",
                                address="10.8.0.10",
                                netmask="24",
                            )
                        ],
                        type_hint="tunnel",
                    ),
                    NetworkInterface(
                        name="en0",
                        is_up=True,
                        addresses=[
                            InterfaceAddress(
                                family="ipv4",
                                address="192.168.1.50",
                                netmask="24",
                            )
                        ],
                        type_hint="ethernet",
                    ),
                ]
            ),
            RouteSummary(
                default_gateway="192.168.1.1",
                default_interface="en0",
                has_default_route=True,
                routes=[
                    RouteEntry(
                        destination="default",
                        gateway="192.168.1.1",
                        interface="en0",
                    ),
                    RouteEntry(
                        destination="10.20/16",
                        gateway="10.8.0.1",
                        interface="utun3",
                    ),
                ],
                default_route_state="present",
            ),
        )

        self.assertEqual(len(vpn_state.signals), 1)
        self.assertEqual(vpn_state.signals[0].signal_type, "route-owned-tunnel-heuristic")


if __name__ == "__main__":
    unittest.main()
