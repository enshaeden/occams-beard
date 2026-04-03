"""Tests for deterministic findings rules."""

from __future__ import annotations

import unittest

from occams_beard.findings import evaluate_selected_findings
from occams_beard.models import (
    CollectedFacts,
    ConnectivityState,
    CpuState,
    DnsResolutionCheck,
    DnsState,
    DiskVolume,
    HostBasics,
    InterfaceAddress,
    MemoryState,
    NetworkInterface,
    NetworkState,
    ResourceState,
    RouteSummary,
    ServiceCheck,
    ServiceState,
    TcpConnectivityCheck,
    TcpTarget,
    TraceHop,
    TraceResult,
    VpnSignal,
    VpnState,
)


def build_base_facts() -> CollectedFacts:
    """Create a reusable baseline fact set for rule tests."""

    return CollectedFacts(
        host=HostBasics(
            hostname="workstation-01",
            operating_system="Linux",
            kernel="6.8.0",
            current_user="operator",
            uptime_seconds=7200,
        ),
        resources=ResourceState(
            cpu=CpuState(logical_cpus=8, utilization_percent_estimate=35.0),
            memory=MemoryState(
                total_bytes=16 * 1024**3,
                available_bytes=8 * 1024**3,
                free_bytes=6 * 1024**3,
                pressure_level="normal",
            ),
            disks=[],
        ),
        network=NetworkState(
            interfaces=[
                NetworkInterface(
                    name="eth0",
                    is_up=True,
                    addresses=[
                        InterfaceAddress(
                            family="ipv4",
                            address="192.168.1.50",
                            netmask="24",
                            is_loopback=False,
                        )
                    ],
                    type_hint="ethernet",
                )
            ],
            local_addresses=["192.168.1.50"],
            active_interfaces=["eth0"],
            route_summary=RouteSummary(
                default_gateway="192.168.1.1",
                default_interface="eth0",
                has_default_route=True,
                routes=[],
            ),
        ),
        dns=DnsState(
            resolvers=["1.1.1.1"],
            checks=[DnsResolutionCheck(hostname="github.com", success=True, resolved_addresses=["140.82.114.3"])],
        ),
        connectivity=ConnectivityState(
            internet_reachable=True,
            tcp_checks=[
                TcpConnectivityCheck(
                    target=TcpTarget(host="github.com", port=443),
                    success=True,
                    latency_ms=25.0,
                )
            ],
            ping_checks=[],
            trace_results=[],
        ),
        vpn=VpnState(signals=[]),
        services=ServiceState(checks=[]),
    )


class FindingsTests(unittest.TestCase):
    """Validate deterministic findings behavior."""

    def test_no_default_route_and_no_connectivity_maps_to_local_network(self) -> None:
        facts = build_base_facts()
        facts.network.route_summary = RouteSummary(
            default_gateway=None,
            default_interface=None,
            has_default_route=False,
            routes=[],
        )
        facts.connectivity.internet_reachable = False
        facts.connectivity.tcp_checks = [
            TcpConnectivityCheck(target=TcpTarget(host="github.com", port=443), success=False, error="timeout"),
            TcpConnectivityCheck(target=TcpTarget(host="1.1.1.1", port=53), success=False, error="timeout"),
        ]

        findings, probable_fault_domain = evaluate_selected_findings(
            facts,
            ["routing", "connectivity", "network"],
        )

        self.assertEqual(probable_fault_domain, "local_network")
        self.assertEqual(findings[0].identifier, "no-default-route-no-internet")

    def test_dns_failure_with_raw_ip_success_maps_to_dns(self) -> None:
        facts = build_base_facts()
        facts.dns.checks = [DnsResolutionCheck(hostname="github.com", success=False, error="temporary failure")]
        facts.connectivity.tcp_checks = [
            TcpConnectivityCheck(target=TcpTarget(host="1.1.1.1", port=53), success=True, latency_ms=10.0)
        ]

        findings, probable_fault_domain = evaluate_selected_findings(
            facts,
            ["dns", "connectivity"],
        )

        self.assertEqual(probable_fault_domain, "dns")
        self.assertEqual(findings[0].identifier, "dns-failure-raw-ip-success")

    def test_route_and_dns_success_with_external_tcp_failures_maps_to_internet_edge(self) -> None:
        facts = build_base_facts()
        facts.dns.checks = [
            DnsResolutionCheck(hostname="github.com", success=True, resolved_addresses=["140.82.114.3"])
        ]
        facts.connectivity.internet_reachable = False
        facts.connectivity.tcp_checks = [
            TcpConnectivityCheck(target=TcpTarget(host="github.com", port=443), success=False, error="timeout"),
            TcpConnectivityCheck(target=TcpTarget(host="1.1.1.1", port=53), success=False, error="refused"),
        ]

        findings, probable_fault_domain = evaluate_selected_findings(
            facts,
            ["routing", "dns", "connectivity"],
        )

        self.assertEqual(probable_fault_domain, "internet_edge")
        self.assertEqual(findings[0].identifier, "route-and-dns-ok-external-tcp-failure")

    def test_default_route_present_but_inactive_interface_maps_to_local_network(self) -> None:
        facts = build_base_facts()
        facts.network.active_interfaces = ["eth1"]
        facts.connectivity.internet_reachable = False
        facts.connectivity.tcp_checks = [
            TcpConnectivityCheck(target=TcpTarget(host="github.com", port=443), success=False, error="timeout"),
            TcpConnectivityCheck(target=TcpTarget(host="1.1.1.1", port=53), success=False, error="timeout"),
        ]

        findings, probable_fault_domain = evaluate_selected_findings(
            facts,
            ["network", "routing", "connectivity"],
        )

        self.assertEqual(probable_fault_domain, "local_network")
        self.assertEqual(findings[0].identifier, "default-route-present-but-inconsistent")
        self.assertIn("not collected as active", " ".join(findings[0].evidence))

    def test_suspect_default_route_blocks_overconfident_internet_edge_finding(self) -> None:
        facts = build_base_facts()
        facts.network.route_summary = RouteSummary(
            default_gateway="10.10.10.1",
            default_interface="eth0",
            has_default_route=True,
            routes=[],
            default_route_state="suspect",
            observations=["Default route exists but is on-link without an explicit gateway."],
        )
        facts.connectivity.internet_reachable = False
        facts.connectivity.tcp_checks = [
            TcpConnectivityCheck(target=TcpTarget(host="github.com", port=443), success=False, error="timeout"),
            TcpConnectivityCheck(target=TcpTarget(host="1.1.1.1", port=53), success=False, error="timeout"),
        ]

        findings, probable_fault_domain = evaluate_selected_findings(
            facts,
            ["network", "routing", "dns", "connectivity"],
        )

        self.assertEqual(probable_fault_domain, "local_network")
        self.assertEqual(findings[0].identifier, "default-route-present-but-inconsistent")
        self.assertNotIn("route-and-dns-ok-external-tcp-failure", [finding.identifier for finding in findings])

    def test_partial_dns_success_is_heuristic_dns_finding(self) -> None:
        facts = build_base_facts()
        facts.dns.checks = [
            DnsResolutionCheck(hostname="github.com", success=True, resolved_addresses=["140.82.114.3"]),
            DnsResolutionCheck(hostname="python.org", success=False, error="temporary failure"),
        ]

        findings, _probable_fault_domain = evaluate_selected_findings(
            facts,
            ["dns", "connectivity"],
        )

        identifiers = [finding.identifier for finding in findings]
        self.assertIn("dns-partial-resolution", identifiers)
        partial_finding = next(finding for finding in findings if finding.identifier == "dns-partial-resolution")
        self.assertTrue(partial_finding.heuristic)

    def test_active_interface_without_address_maps_to_local_network(self) -> None:
        facts = build_base_facts()
        facts.network.interfaces = [
            NetworkInterface(name="eth0", is_up=True, addresses=[], type_hint="ethernet")
        ]
        facts.network.local_addresses = []
        facts.network.route_summary = RouteSummary(
            default_gateway=None,
            default_interface=None,
            has_default_route=False,
            routes=[],
        )

        findings, probable_fault_domain = evaluate_selected_findings(
            facts,
            ["network", "routing"],
        )

        self.assertEqual(probable_fault_domain, "local_network")
        self.assertEqual(findings[0].identifier, "active-interface-no-local-address")

    def test_selected_service_failure_with_internet_reachability_maps_to_upstream_network(self) -> None:
        facts = build_base_facts()
        facts.services = ServiceState(
            checks=[
                ServiceCheck(
                    target=TcpTarget(host="status.example.com", port=443, label="status-api"),
                    success=False,
                    error="timeout",
                )
            ]
        )

        findings, probable_fault_domain = evaluate_selected_findings(
            facts,
            ["services", "connectivity"],
        )

        self.assertEqual(probable_fault_domain, "upstream_network")
        self.assertEqual(findings[0].identifier, "internet-ok-selected-service-failure")

    def test_low_disk_space_generates_local_host_finding(self) -> None:
        facts = build_base_facts()
        facts.resources.disks = [
            DiskVolume(
                path="/",
                total_bytes=1000,
                used_bytes=950,
                free_bytes=50,
                percent_used=95.0,
            )
        ]

        findings, probable_fault_domain = evaluate_selected_findings(
            facts,
            ["storage"],
        )

        self.assertEqual(probable_fault_domain, "local_host")
        self.assertTrue(any(finding.identifier.startswith("low-disk-space-") for finding in findings))

    def test_vpn_signal_with_private_target_failure_is_heuristic(self) -> None:
        facts = build_base_facts()
        facts.vpn = VpnState(
            signals=[
                VpnSignal(
                    interface_name="utun2",
                    signal_type="interface-name-and-address-heuristic",
                    description="Tunnel-like interface name detected with a usable address.",
                    active=True,
                    confidence=0.75,
                    address_count=1,
                )
            ]
        )
        facts.network.route_summary = RouteSummary(
            default_gateway="10.8.0.1",
            default_interface="utun2",
            has_default_route=True,
            routes=[],
        )
        facts.services = ServiceState(
            checks=[
                ServiceCheck(
                    target=TcpTarget(host="10.0.0.10", port=443),
                    success=False,
                    error="timeout",
                )
            ]
        )

        findings, probable_fault_domain = evaluate_selected_findings(
            facts,
            ["vpn", "services"],
        )

        self.assertEqual(probable_fault_domain, "vpn")
        self.assertTrue(findings[0].heuristic)

    def test_partial_traceroute_generates_upstream_network_finding(self) -> None:
        facts = build_base_facts()
        facts.connectivity.trace_results = [
            TraceResult(
                target="github.com",
                ran=True,
                success=False,
                partial=True,
                target_address="140.82.114.3",
                last_responding_hop=3,
                hops=[
                    TraceHop(hop=1, host="192.168.1.1", address="192.168.1.1", latency_ms=1.2),
                    TraceHop(hop=2, host="10.0.0.1", address="10.0.0.1", latency_ms=8.5),
                    TraceHop(hop=3, host="203.0.113.1", address="203.0.113.1", latency_ms=15.0),
                    TraceHop(hop=4, host=None, address=None, latency_ms=None, note="timeout"),
                ],
            )
        ]

        findings, probable_fault_domain = evaluate_selected_findings(
            facts,
            ["connectivity"],
        )

        self.assertEqual(probable_fault_domain, "upstream_network")
        self.assertEqual(findings[0].identifier, "partial-trace-github.com")
        self.assertIn("last received a response at hop 3", findings[0].evidence[0])


if __name__ == "__main__":
    unittest.main()
