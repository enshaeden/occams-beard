"""Tests for deterministic findings rules."""

from __future__ import annotations

import unittest

from endpoint_diagnostics_lab.findings import evaluate_selected_findings
from endpoint_diagnostics_lab.models import (
    CollectedFacts,
    ConnectivityState,
    CpuState,
    DnsResolutionCheck,
    DnsState,
    DiskVolume,
    HostBasics,
    MemoryState,
    NetworkState,
    ResourceState,
    RouteSummary,
    ServiceCheck,
    ServiceState,
    TcpConnectivityCheck,
    TcpTarget,
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
            ["routing", "connectivity"],
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
                    signal_type="interface-name-heuristic",
                    description="Tunnel-like interface name detected.",
                    active=True,
                    confidence=0.75,
                )
            ]
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


if __name__ == "__main__":
    unittest.main()
