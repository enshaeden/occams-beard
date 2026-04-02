"""Tests for human-readable report rendering."""

from __future__ import annotations

import unittest

from endpoint_diagnostics_lab.models import (
    CollectedFacts,
    ConnectivityState,
    CpuState,
    DiagnosticWarning,
    DnsResolutionCheck,
    DnsState,
    EndpointDiagnosticResult,
    Finding,
    HostBasics,
    InterfaceAddress,
    NetworkInterface,
    MemoryState,
    Metadata,
    NetworkState,
    PlatformInfo,
    ResourceState,
    RouteSummary,
    ServiceCheck,
    ServiceState,
    TraceHop,
    TraceResult,
    TcpConnectivityCheck,
    TcpTarget,
    VpnState,
)
from endpoint_diagnostics_lab.report import render_report


class ReportOutputTests(unittest.TestCase):
    """Validate human-readable report output."""

    def test_render_report_includes_required_sections_and_evidence_labels(self) -> None:
        result = EndpointDiagnosticResult(
            metadata=Metadata(
                project_name="endpoint-diagnostics-lab",
                version="0.1.0",
                generated_at="2026-04-01T00:00:00+00:00",
                elapsed_ms=100,
                selected_checks=["network", "dns", "connectivity", "services"],
            ),
            platform=PlatformInfo(
                system="Linux",
                release="6.8.0",
                version="demo",
                machine="x86_64",
                python_version="3.11.9",
            ),
            facts=CollectedFacts(
                host=HostBasics(
                    hostname="demo-host",
                    operating_system="Linux",
                    kernel="6.8.0",
                    current_user="operator",
                    uptime_seconds=600,
                ),
                resources=ResourceState(
                    cpu=CpuState(logical_cpus=4, utilization_percent_estimate=12.5),
                    memory=MemoryState(
                        total_bytes=1024**3,
                        available_bytes=512 * 1024**2,
                        free_bytes=256 * 1024**2,
                        pressure_level="normal",
                    ),
                    disks=[],
                ),
                network=NetworkState(
                    interfaces=[
                        NetworkInterface(
                            name="eth0",
                            is_up=True,
                            mtu=1500,
                            addresses=[
                                InterfaceAddress(
                                    family="ipv4",
                                    address="192.168.1.50",
                                    netmask="24",
                                )
                            ],
                        )
                    ],
                    local_addresses=["192.168.1.50"],
                    active_interfaces=["eth0"],
                    arp_neighbors=[],
                    route_summary=RouteSummary(
                        default_gateway="192.168.1.1",
                        default_interface="eth0",
                        has_default_route=True,
                        routes=[],
                        default_route_state="present",
                        observations=[],
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
                            target=TcpTarget(host="github.com", port=443, label="github-https"),
                            success=True,
                            latency_ms=23.1,
                            ip_used="140.82.114.3",
                        )
                    ],
                    trace_results=[
                        TraceResult(
                            target="github.com",
                            ran=True,
                            success=False,
                            partial=True,
                            target_address="140.82.114.3",
                            last_responding_hop=2,
                            hops=[
                                TraceHop(hop=1, host="192.168.1.1", address="192.168.1.1", latency_ms=1.0),
                                TraceHop(hop=2, host="10.0.0.1", address="10.0.0.1", latency_ms=4.0),
                                TraceHop(hop=3, host=None, address=None, latency_ms=None, note="timeout"),
                            ],
                        )
                    ],
                ),
                vpn=VpnState(),
                services=ServiceState(
                    checks=[
                        ServiceCheck(
                            target=TcpTarget(host="status.example.com", port=443, label="status-api"),
                            success=False,
                            error="timeout",
                        )
                    ]
                ),
            ),
            findings=[
                Finding(
                    identifier="internet-ok-selected-service-failure",
                    severity="medium",
                    title="Generic internet reachability works but selected service checks fail",
                    summary="Baseline external path checks succeeded, but every configured public service check failed.",
                    evidence=[
                        "Generic internet reachability checks succeeded.",
                        "Failed configured public services: status-api (timeout).",
                    ],
                    probable_cause="The failure is more likely isolated to the intended service path than to general internet access.",
                    fault_domain="upstream_network",
                    confidence=0.79,
                )
            ],
            probable_fault_domain="upstream_network",
            warnings=[
                DiagnosticWarning(
                    domain="connectivity",
                    code="trace-unavailable",
                    message="Traceroute command is unavailable on this endpoint.",
                )
            ],
        )

        text = render_report(result, json_path="/tmp/report.json")

        self.assertIn("Summary", text)
        self.assertIn("Key Findings", text)
        self.assertIn("Derived finding:", text)
        self.assertIn("Observed fact:", text)
        self.assertIn("Generic Reachability Checks", text)
        self.assertIn("DNS Resolution", text)
        self.assertIn("Configured Service Checks", text)
        self.assertIn("Warnings and degraded checks", text)
        self.assertIn("Fault-domain basis", text)
        self.assertIn("Interface MTUs: eth0=1500", text)
        self.assertIn("ARP neighbors: none collected", text)
        self.assertIn("Default route state: not collected", text)
        self.assertIn("Trace github.com: partial, last response at hop 2, target 140.82.114.3 not reached", text)
        self.assertIn("/tmp/report.json", text)

    def test_render_report_marks_heuristic_findings(self) -> None:
        result = EndpointDiagnosticResult(
            metadata=Metadata(
                project_name="endpoint-diagnostics-lab",
                version="0.1.0",
                generated_at="2026-04-01T00:00:00+00:00",
                elapsed_ms=100,
                selected_checks=["vpn", "services"],
            ),
            platform=PlatformInfo(
                system="macOS",
                release="15.0",
                version="demo",
                machine="arm64",
                python_version="3.11.9",
            ),
            facts=CollectedFacts(
                host=HostBasics(
                    hostname="demo-host",
                    operating_system="Darwin",
                    kernel="24.0.0",
                    current_user="operator",
                    uptime_seconds=600,
                ),
                resources=ResourceState(
                    cpu=CpuState(logical_cpus=4),
                    memory=MemoryState(total_bytes=None, available_bytes=None, free_bytes=None),
                    disks=[],
                ),
                network=NetworkState(
                    interfaces=[
                        NetworkInterface(name="utun2", is_up=True, mtu=1380)
                    ],
                    local_addresses=["10.8.0.10"],
                    active_interfaces=["utun2"],
                    route_summary=RouteSummary(
                        default_gateway="10.8.0.1",
                        default_interface="utun2",
                        has_default_route=True,
                        routes=[],
                        default_route_state="suspect",
                        observations=["Default route uses link-scoped gateway link#15, so next-hop reachability is less explicit."],
                    ),
                ),
                dns=DnsState(),
                connectivity=ConnectivityState(internet_reachable=False),
                vpn=VpnState(),
                services=ServiceState(),
            ),
            findings=[
                Finding(
                    identifier="vpn-signal-private-resource-failure",
                    severity="medium",
                    title="VPN or tunnel appears active while private targets remain unreachable",
                    summary="A VPN-like interface is present, but private resource checks still failed.",
                    evidence=[
                        "VPN heuristic matched interface utun2 (interface-name-and-address-heuristic, confidence 0.75, 1 usable address)."
                    ],
                    probable_cause="The tunnel may be established, but its routes, security policy, or remote network path may be incomplete.",
                    fault_domain="vpn",
                    confidence=0.82,
                    heuristic=True,
                )
            ],
            probable_fault_domain="vpn",
        )

        text = render_report(result)

        self.assertIn("Heuristic conclusion:", text)
        self.assertIn("heuristic", text)
        self.assertIn("Internet reachable: not collected", text)
        self.assertIn("Default route present: not collected", text)


if __name__ == "__main__":
    unittest.main()
