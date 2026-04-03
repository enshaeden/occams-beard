"""Shared test helpers for diagnostics result fixtures."""

from __future__ import annotations

from occams_beard.models import (
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
    TcpConnectivityCheck,
    TcpTarget,
    VpnState,
)


def build_sample_result() -> EndpointDiagnosticResult:
    """Create a representative diagnostics result for UI and runner tests."""

    return EndpointDiagnosticResult(
        metadata=Metadata(
            project_name="occams-beard",
            version="0.1.0",
            generated_at="2026-04-01T00:00:00+00:00",
            elapsed_ms=125,
            selected_checks=["network", "routing", "dns", "connectivity", "services"],
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
                cpu=CpuState(logical_cpus=8, utilization_percent_estimate=18.2),
                memory=MemoryState(
                    total_bytes=8 * 1024**3,
                    available_bytes=4 * 1024**3,
                    free_bytes=3 * 1024**3,
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
                            InterfaceAddress(family="ipv4", address="192.168.1.50", netmask="24")
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
                ),
            ),
            dns=DnsState(
                resolvers=["1.1.1.1"],
                checks=[
                    DnsResolutionCheck(
                        hostname="github.com",
                        success=True,
                        resolved_addresses=["140.82.114.3"],
                    )
                ],
            ),
            connectivity=ConnectivityState(
                internet_reachable=True,
                tcp_checks=[
                    TcpConnectivityCheck(
                        target=TcpTarget(host="github.com", port=443, label="github-https"),
                        success=True,
                        latency_ms=28.4,
                        ip_used="140.82.114.3",
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
                identifier="service-path-issue",
                severity="medium",
                title="Generic reachability works but a configured service fails",
                summary="Baseline reachability succeeded, but the configured service check failed.",
                evidence=[
                    "github.com:443 succeeded.",
                    "status-api failed with timeout.",
                ],
                probable_cause="The issue appears isolated to the intended service path.",
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
