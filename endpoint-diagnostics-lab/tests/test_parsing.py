"""Tests for representative command output parsing."""

from __future__ import annotations

import unittest

from endpoint_diagnostics_lab.utils.parsing import (
    parse_ifconfig,
    parse_ip_addr_show,
    parse_linux_ip_route,
    parse_route_print,
)
from endpoint_diagnostics_lab.platform.macos import _parse_uptime_seconds


class ParsingTests(unittest.TestCase):
    """Validate representative parser behavior."""

    def test_parse_linux_ip_route_extracts_default(self) -> None:
        output = """
default via 192.168.1.1 dev en0 proto dhcp metric 100
10.0.0.0/24 dev tun0 proto kernel scope link src 10.0.0.10
192.168.1.0/24 dev en0 proto kernel scope link src 192.168.1.50 metric 100
""".strip()

        parsed = parse_linux_ip_route(output)

        self.assertEqual(parsed["default_gateway"], "192.168.1.1")
        self.assertEqual(parsed["default_interface"], "en0")
        self.assertTrue(parsed["has_default_route"])
        self.assertEqual(len(parsed["routes"]), 3)

    def test_parse_ip_addr_show_extracts_addresses(self) -> None:
        output = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000
    link/ether 52:54:00:12:34:56 brd ff:ff:ff:ff:ff:ff
    inet 192.168.1.50/24 brd 192.168.1.255 scope global dynamic eth0
    inet6 fe80::5054:ff:fe12:3456/64 scope link
""".strip()

        parsed = parse_ip_addr_show(output)

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[1]["name"], "eth0")
        self.assertTrue(parsed[1]["is_up"])
        self.assertEqual(parsed[1]["mac_address"], "52:54:00:12:34:56")
        self.assertEqual(parsed[1]["addresses"][0]["address"], "192.168.1.50")

    def test_parse_ifconfig_extracts_unix_interface_inventory(self) -> None:
        output = """
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
    ether aa:bb:cc:dd:ee:ff
    inet 192.168.1.25 netmask 0xffffff00 broadcast 192.168.1.255
utun2: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380
    inet 10.8.0.10 --> 10.8.0.10 netmask 0xffffff00
""".strip()

        parsed = parse_ifconfig(output)

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["name"], "en0")
        self.assertEqual(parsed[1]["name"], "utun2")
        self.assertTrue(parsed[1]["is_up"])

    def test_parse_route_print_extracts_windows_default_route(self) -> None:
        output = """
===========================================================================
IPv4 Route Table
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0      10.10.10.1    10.10.10.50     25
        10.10.10.0    255.255.255.0         On-link     10.10.10.50    281
""".strip()

        parsed = parse_route_print(output)

        self.assertEqual(parsed["default_gateway"], "10.10.10.1")
        self.assertEqual(parsed["default_interface"], "10.10.10.50")
        self.assertEqual(parsed["routes"][0]["destination"], "default")

    def test_parse_macos_uptime_fallback(self) -> None:
        output = "23:41  up 1 day,  2:34, 4 users, load averages: 2.08 1.95 1.90"

        uptime_seconds = _parse_uptime_seconds(output)

        self.assertEqual(uptime_seconds, 95640)


if __name__ == "__main__":
    unittest.main()
