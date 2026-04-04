"""Tests for representative command output parsing."""

from __future__ import annotations

import unittest
from pathlib import Path

from occams_beard.platform.macos import _parse_uptime_seconds
from occams_beard.utils.parsing import (
    parse_arp_table,
    parse_ifconfig,
    parse_ip_addr_show,
    parse_ip_neigh,
    parse_ipconfig,
    parse_linux_ip_route,
    parse_netstat_rn,
    parse_ping_output,
    parse_powershell_dns_server_list,
    parse_resolv_conf,
    parse_route_get_default,
    parse_route_print,
    parse_scutil_dns,
    parse_traceroute_output,
    parse_windows_ipconfig_dns_servers,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8").strip()


class ParsingTests(unittest.TestCase):
    """Validate representative parser behavior."""

    def test_parse_linux_ip_route_extracts_lowest_metric_default(self) -> None:
        parsed = parse_linux_ip_route(_fixture("linux-ip-route-multiple-defaults.txt"))

        self.assertEqual(parsed["default_gateway"], "10.8.0.1")
        self.assertEqual(parsed["default_interface"], "tun0")
        self.assertEqual(parsed["default_route_state"], "suspect")
        self.assertIn("Multiple default routes were collected", parsed["observations"][0])
        self.assertEqual(len(parsed["routes"]), 4)

    def test_parse_linux_ip_route_marks_unreachable_default_as_suspect(self) -> None:
        parsed = parse_linux_ip_route(_fixture("linux-ip-route-unreachable-default.txt"))

        self.assertTrue(parsed["has_default_route"])
        self.assertEqual(parsed["default_interface"], "lo")
        self.assertEqual(parsed["default_route_state"], "suspect")
        self.assertIn("marked unreachable", " ".join(parsed["observations"]))

    def test_parse_linux_ip_route_prefers_usable_default_over_blackhole(self) -> None:
        parsed = parse_linux_ip_route(_fixture("linux-ip-route-blackhole-default.txt"))

        self.assertEqual(parsed["default_gateway"], "192.168.50.1")
        self.assertEqual(parsed["default_interface"], "eth0")
        self.assertEqual(parsed["default_route_state"], "suspect")
        self.assertTrue(any("blackhole" in note for note in parsed["observations"]))
        self.assertEqual(parsed["routes"][2]["interface"], "tun0")

    def test_parse_linux_ip_route_preserves_split_tunnel_routes(self) -> None:
        parsed = parse_linux_ip_route(_fixture("linux-ip-route-split-tunnel.txt"))

        self.assertEqual(parsed["default_gateway"], "192.168.1.1")
        self.assertEqual(parsed["default_interface"], "eth0")
        self.assertEqual(parsed["default_route_state"], "present")
        self.assertEqual(parsed["routes"][1]["interface"], "tun0")
        self.assertEqual(parsed["routes"][2]["gateway"], "10.20.0.1")

    def test_parse_ip_addr_show_extracts_addresses_and_normalizes_peer_suffixes(self) -> None:
        output = """
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    inet 127.0.0.1/8 scope host lo
2: eth0@if3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000
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

    def test_parse_ifconfig_preserves_tunnel_and_ipv6_variants(self) -> None:
        parsed = parse_ifconfig(_fixture("macos-ifconfig-utun-variants.txt"))

        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["mac_address"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(parsed[1]["name"], "utun3")
        self.assertTrue(parsed[1]["is_up"])
        self.assertEqual(parsed[1]["addresses"][1]["family"], "ipv6")
        self.assertEqual(parsed[2]["name"], "bridge0")

    def test_parse_netstat_rn_marks_link_scoped_default_as_suspect(self) -> None:
        output = """
Routing tables

Internet:
Destination        Gateway            Flags               Netif Expire
default            link#15            UCSIg                 utun2
default            192.168.1.1        UGScg                 en0
192.168.1/24       link#4             UCS                   en0
""".strip()

        parsed = parse_netstat_rn(output)

        self.assertEqual(parsed["default_gateway"], "192.168.1.1")
        self.assertEqual(parsed["default_interface"], "en0")
        self.assertEqual(parsed["default_route_state"], "suspect")
        self.assertTrue(any("link-scoped gateway" in note for note in parsed["observations"]))

    def test_parse_netstat_rn_preserves_macos_split_tunnel_routes(self) -> None:
        parsed = parse_netstat_rn(_fixture("macos-netstat-rn-split-tunnel.txt"))

        self.assertEqual(parsed["default_gateway"], "192.168.1.1")
        self.assertEqual(parsed["default_interface"], "en0")
        self.assertEqual(parsed["default_route_state"], "suspect")
        self.assertTrue(any("link-scoped gateway" in note for note in parsed["observations"]))
        self.assertEqual(parsed["routes"][2]["interface"], "utun3")
        self.assertEqual(parsed["routes"][3]["gateway"], "10.8.0.1")

    def test_parse_netstat_rn_supports_legacy_linux_route_table_layout(self) -> None:
        parsed = parse_netstat_rn(_fixture("linux-netstat-rn-legacy.txt"))

        self.assertEqual(parsed["default_gateway"], "192.168.122.1")
        self.assertEqual(parsed["default_interface"], "ens3")
        self.assertEqual(parsed["default_route_state"], "present")
        self.assertEqual(parsed["routes"][1]["interface"], "tun0")

    def test_parse_netstat_rn_ignores_internet6_section_when_ipv4_section_exists(self) -> None:
        output = """
Routing tables

Internet:
Destination        Gateway            Flags               Netif Expire
default            192.168.1.1        UGScg                 en0

Internet6:
Destination                             Gateway
default                                 fe80::%utun0
""".strip()

        parsed = parse_netstat_rn(output)

        self.assertEqual(parsed["default_gateway"], "192.168.1.1")
        self.assertEqual(parsed["default_interface"], "en0")
        self.assertEqual(parsed["default_route_state"], "present")
        self.assertEqual(len(parsed["routes"]), 1)

    def test_parse_route_print_prefers_usable_windows_default_and_records_observation(self) -> None:
        parsed = parse_route_print(_fixture("windows-route-print-on-link.txt"))

        self.assertEqual(parsed["default_gateway"], "10.10.10.1")
        self.assertEqual(parsed["default_interface"], "10.10.10.50")
        self.assertEqual(parsed["default_route_state"], "suspect")
        self.assertTrue(any("on-link" in note for note in parsed["observations"]))
        self.assertEqual(
            parsed["routes"][0]["note"],
            "Default route exists but is on-link without an explicit gateway.",
        )

    def test_parse_route_print_preserves_split_tunnel_routes(self) -> None:
        parsed = parse_route_print(_fixture("windows-route-print-vpn-split-tunnel.txt"))

        self.assertEqual(parsed["default_gateway"], "192.168.1.1")
        self.assertEqual(parsed["default_interface"], "192.168.1.50")
        self.assertEqual(parsed["default_route_state"], "suspect")
        self.assertTrue(any("on-link" in note for note in parsed["observations"]))
        self.assertEqual(parsed["routes"][2]["interface"], "10.8.0.10")
        self.assertEqual(parsed["routes"][3]["gateway"], "10.8.0.1")

    def test_parse_route_print_supports_localized_section_headers(self) -> None:
        parsed = parse_route_print(_fixture("windows-route-print-localized-headers.txt"))

        self.assertEqual(parsed["default_gateway"], "10.10.10.1")
        self.assertEqual(parsed["default_interface"], "10.10.10.50")
        self.assertEqual(parsed["default_route_state"], "suspect")
        self.assertTrue(any("on-link" in note for note in parsed["observations"]))
        self.assertEqual(parsed["routes"][2]["gateway"], "10.8.0.1")

    def test_parse_route_print_records_parse_warning_for_malformed_numeric_line(self) -> None:
        parsed = parse_route_print(_fixture("windows-route-print-malformed-vpn.txt"))

        self.assertEqual(parsed["default_gateway"], "10.8.0.1")
        self.assertEqual(parsed["default_interface"], "10.8.0.10")
        self.assertEqual(parsed["default_route_state"], "suspect")
        self.assertTrue(any("on-link" in note for note in parsed["observations"]))
        self.assertEqual(len(parsed["parse_warnings"]), 1)
        self.assertIn("malformed Windows route line", parsed["parse_warnings"][0])

    def test_parse_route_get_default_extracts_gateway_and_interface(self) -> None:
        output = """
   route to: default
destination: default
       mask: default
    gateway: 192.168.1.1
  interface: en0
""".strip()

        parsed = parse_route_get_default(output)

        self.assertEqual(parsed["default_gateway"], "192.168.1.1")
        self.assertEqual(parsed["default_interface"], "en0")
        self.assertTrue(parsed["has_default_route"])
        self.assertEqual(parsed["default_route_state"], "present")

    def test_parse_ipconfig_extracts_common_windows_variants(self) -> None:
        parsed = parse_ipconfig(_fixture("windows-ipconfig-variants.txt"))

        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["name"], "Loopback Pseudo-Interface 1")
        self.assertEqual(parsed[0]["addresses"][0]["address"], "::1")
        self.assertTrue(parsed[1]["is_up"])
        self.assertEqual(parsed[1]["addresses"][1]["family"], "ipv6")
        self.assertEqual(parsed[1]["addresses"][1]["address"], "2001:db8::1234:5678")
        self.assertFalse(parsed[2]["is_up"])

    def test_parse_ipconfig_extracts_vpn_adapter_addresses(self) -> None:
        output = """
PPP adapter Contoso Secure Access:

   Media State . . . . . . . . . . . : Media connected
   IPv4 Address. . . . . . . . . . . : 10.8.0.10
   Link-local IPv6 Address . . . . . : fe80::1234:5678:abcd:ef12
""".strip()

        parsed = parse_ipconfig(output)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["name"], "Contoso Secure Access")
        self.assertTrue(parsed[0]["is_up"])
        self.assertEqual(parsed[0]["addresses"][0]["address"], "10.8.0.10")
        self.assertEqual(parsed[0]["addresses"][1]["family"], "ipv6")

    def test_parse_ipconfig_handles_connected_and_disconnected_tunnels(self) -> None:
        parsed = parse_ipconfig(_fixture("windows-ipconfig-tunnel-variants.txt"))

        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[1]["name"], "WireGuard Tunnel")
        self.assertTrue(parsed[1]["is_up"])
        self.assertEqual(parsed[1]["addresses"][1]["family"], "ipv6")
        self.assertEqual(parsed[2]["name"], "Contoso Legacy VPN")
        self.assertFalse(parsed[2]["is_up"])

    def test_parse_macos_uptime_fallback(self) -> None:
        output = "23:41  up 1 day,  2:34, 4 users, load averages: 2.08 1.95 1.90"

        uptime_seconds = _parse_uptime_seconds(output)

        self.assertEqual(uptime_seconds, 95640)

    def test_parse_traceroute_output_marks_windows_timeouts_and_hostnames(self) -> None:
        parsed = parse_traceroute_output(_fixture("windows-tracert-partial.txt"))

        self.assertEqual(len(parsed), 4)
        self.assertEqual(parsed[0]["address"], "192.168.1.1")
        self.assertEqual(parsed[0]["latency_ms"], 1.0)
        self.assertEqual(parsed[1]["host"], "ae1.cr1.example.net")
        self.assertEqual(parsed[1]["address"], "203.0.113.10")
        self.assertEqual(parsed[2]["note"], "request timed out.")
        self.assertEqual(parsed[3]["note"], "destination net unreachable.")

    def test_parse_traceroute_output_marks_windows_general_failure(self) -> None:
        parsed = parse_traceroute_output(_fixture("windows-tracert-general-failure.txt"))

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["note"], "general failure.")
        self.assertEqual(parsed[1]["note"], "request timed out.")

    def test_parse_traceroute_output_parses_complete_windows_trace(self) -> None:
        parsed = parse_traceroute_output(_fixture("windows-tracert-complete.txt"))

        self.assertEqual(len(parsed), 4)
        self.assertEqual(parsed[0]["latency_ms"], 1.0)
        self.assertEqual(parsed[2]["host"], "ae1.cr1.example.net")
        self.assertEqual(parsed[2]["address"], "203.0.113.10")
        self.assertEqual(parsed[3]["address"], "93.184.216.34")
        self.assertIsNone(parsed[3]["note"])

    def test_parse_traceroute_output_accepts_bytes_output(self) -> None:
        output = (
            b"  1  192.168.1.1  1.123 ms  1.234 ms  1.345 ms\n"
            b"  2  * * *\n"
            b"  3  203.0.113.10  10.000 ms  11.000 ms  12.000 ms\n"
        )

        parsed = parse_traceroute_output(output)

        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["address"], "192.168.1.1")
        self.assertEqual(parsed[1]["note"], "timeout")
        self.assertEqual(parsed[2]["latency_ms"], 11.0)

    def test_parse_ping_output_extracts_unix_latency_and_packet_loss(self) -> None:
        output = """
PING github.com (140.82.112.3): 56 data bytes
--- github.com ping statistics ---
10 packets transmitted, 10 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 12.111/15.222/22.333/1.444 ms
""".strip()

        parsed = parse_ping_output(output)

        self.assertEqual(parsed["average_latency_ms"], 15.222)
        self.assertEqual(parsed["packet_loss_percent"], 0.0)

    def test_parse_ping_output_accepts_bytes_output(self) -> None:
        output = (
            b"PING github.com (140.82.112.3): 56 data bytes\n"
            b"--- github.com ping statistics ---\n"
            b"10 packets transmitted, 9 packets received, 10.0% packet loss\n"
            b"round-trip min/avg/max/stddev = 12.111/15.222/22.333/1.444 ms\n"
        )

        parsed = parse_ping_output(output)

        self.assertEqual(parsed["average_latency_ms"], 15.222)
        self.assertEqual(parsed["packet_loss_percent"], 10.0)

    def test_parse_ip_neigh_extracts_neighbor_cache(self) -> None:
        output = """
192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
10.8.0.1 dev tun0 FAILED
""".strip()

        parsed = parse_ip_neigh(output)

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["mac_address"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(parsed[1]["interface"], "tun0")
        self.assertEqual(parsed[1]["state"], "FAILED")

    def test_parse_arp_table_supports_windows_and_macos_formats(self) -> None:
        output = """
Interface: 10.10.10.50 --- 0x7
  Internet Address      Physical Address      Type
  10.10.10.1            aa-bb-cc-dd-ee-ff     dynamic
? (192.168.1.1) at 88:36:6c:12:34:56 on en0 ifscope [ethernet]
""".strip()

        parsed = parse_arp_table(output)

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["interface"], "10.10.10.50")
        self.assertEqual(parsed[0]["mac_address"], "aa:bb:cc:dd:ee:ff")
        self.assertEqual(parsed[1]["interface"], "en0")

    def test_parse_resolv_conf_ignores_search_and_options_lines(self) -> None:
        parsed = parse_resolv_conf(_fixture("linux-resolv-conf-variants.txt"))

        self.assertEqual(parsed, ["10.0.0.53", "1.1.1.1"])

    def test_parse_resolv_conf_preserves_ipv6_nameservers(self) -> None:
        parsed = parse_resolv_conf(_fixture("linux-resolv-conf-ipv6-variants.txt"))

        self.assertEqual(
            parsed,
            ["10.0.0.53", "2606:4700:4700::1111", "1.1.1.1"],
        )

    def test_parse_scutil_dns_dedupes_scoped_nameservers(self) -> None:
        parsed = parse_scutil_dns(_fixture("macos-scutil-dns-variants.txt"))

        self.assertEqual(
            parsed,
            ["10.0.0.53", "2001:4860:4860::8888", "10.8.0.53", "fe80::1%utun3"],
        )

    def test_parse_powershell_dns_server_list_dedupes_and_strips_blank_lines(self) -> None:
        parsed = parse_powershell_dns_server_list(
            _fixture("windows-dns-server-addresses-variants.txt")
        )

        self.assertEqual(parsed, ["10.0.0.2", "fe80::1", "1.1.1.1"])

    def test_parse_windows_ipconfig_dns_servers_handles_continuation_lines(self) -> None:
        output = """
Ethernet adapter Ethernet:

   Connection-specific DNS Suffix  . : corp.example
   DNS Servers . . . . . . . . . . . : 10.0.0.2
                                       fe80::1
                                       1.1.1.1

Wireless LAN adapter Wi-Fi:

   Media State . . . . . . . . . . . : Media disconnected
""".strip()

        parsed = parse_windows_ipconfig_dns_servers(output)

        self.assertEqual(parsed, ["10.0.0.2", "fe80::1", "1.1.1.1"])


if __name__ == "__main__":
    unittest.main()
