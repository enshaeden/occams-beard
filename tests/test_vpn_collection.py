"""Tests for VPN and tunnel signal normalization."""

from __future__ import annotations

import unittest

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

    def test_collect_vpn_state_detects_active_tunnel_interface_without_assuming_default_route(
        self,
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

    def test_collect_vpn_state_adds_default_route_signal_for_tunnel_default_path(self) -> None:
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

        signal_types = {signal.signal_type for signal in vpn_state.signals}
        self.assertEqual(
            signal_types,
            {"interface-name-and-address-heuristic", "default-route-heuristic"},
        )


if __name__ == "__main__":
    unittest.main()
