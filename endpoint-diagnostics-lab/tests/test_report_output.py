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
    MemoryState,
    Metadata,
    NetworkState,
    PlatformInfo,
    ResourceState,
    RouteSummary,
    ServiceState,
    TcpConnectivityCheck,
    TcpTarget,
    VpnState,
)
from endpoint_diagnostics_lab.report import render_report


class ReportOutputTests(unittest.TestCase):
    """Validate human-readable report output."""

    def test_render_report_includes_required_sections(self) -> None:
        result = EndpointDiagnosticResult(
            metadata=Metadata(
                project_name="endpoint-diagnostics-lab",
                version="0.1.0",
                generated_at="2026-04-01T00:00:00+00:00",
                elapsed_ms=100,
                selected_checks=["network", "dns", "connectivity"],
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
                    checks=[DnsResolutionCheck(hostname="github.com", success=True, resolved_addresses=["140.82.114.3"])]
                ),
                connectivity=ConnectivityState(
                    internet_reachable=True,
                    tcp_checks=[
                        TcpConnectivityCheck(
                            target=TcpTarget(host="github.com", port=443),
                            success=True,
                            latency_ms=23.1,
                        )
                    ],
                ),
                vpn=VpnState(),
                services=ServiceState(),
            ),
            findings=[
                Finding(
                    identifier="healthy-baseline",
                    severity="info",
                    title="No major diagnostic findings detected",
                    summary="The collected facts did not match any major fault rule.",
                    evidence=["No deterministic fault signatures triggered."],
                    probable_cause="No major failure domain identified.",
                    fault_domain="healthy",
                    confidence=0.8,
                )
            ],
            probable_fault_domain="healthy",
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
        self.assertIn("System Snapshot", text)
        self.assertIn("Network Snapshot", text)
        self.assertIn("Connectivity Results", text)
        self.assertIn("Probable Fault Domain", text)
        self.assertIn("/tmp/report.json", text)
        self.assertIn("Warnings", text)


if __name__ == "__main__":
    unittest.main()
