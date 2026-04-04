"""Shared test helpers for diagnostics result fixtures."""

from __future__ import annotations

from typing import cast

from occams_beard.assistant import build_guided_experience, enrich_findings
from occams_beard.defaults import DEFAULT_CHECKS, DEFAULT_TCP_TARGETS
from occams_beard.execution import build_execution_records
from occams_beard.findings import evaluate_selected_findings
from occams_beard.models import (
    ArpNeighbor,
    BatteryState,
    CollectedFacts,
    ConnectivityState,
    CpuState,
    DiagnosticWarning,
    DiskVolume,
    DnsResolutionCheck,
    DnsState,
    EndpointDiagnosticResult,
    FaultDomain,
    Finding,
    HostBasics,
    InterfaceAddress,
    MemoryState,
    Metadata,
    NetworkInterface,
    NetworkState,
    PlatformInfo,
    RawCommandCapture,
    ResourceState,
    RouteEntry,
    RouteSummary,
    ServiceCheck,
    ServiceState,
    StorageDeviceHealth,
    TcpConnectivityCheck,
    TcpTarget,
    TraceResult,
    VpnSignal,
    VpnState,
)
from occams_beard.profile_catalog import get_profile
from occams_beard.runner import DiagnosticsRunOptions


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
            battery=BatteryState(present=False),
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


def build_default_run_result() -> EndpointDiagnosticResult:
    options = DiagnosticsRunOptions(
        selected_checks=list(DEFAULT_CHECKS),
        targets=list(DEFAULT_TCP_TARGETS),
        dns_hosts=["github.com", "python.org"],
    )
    facts = CollectedFacts(
        host=HostBasics(
            hostname="workstation-01",
            operating_system="Linux",
            kernel="6.8.0",
            current_user="operator",
            uptime_seconds=86400,
        ),
        resources=ResourceState(
            cpu=CpuState(
                logical_cpus=8,
                load_average_1m=0.62,
                load_average_5m=0.54,
                load_average_15m=0.49,
                utilization_percent_estimate=7.8,
            ),
            memory=MemoryState(
                total_bytes=16 * 1024**3,
                available_bytes=9_600_000_000,
                free_bytes=7_400_000_000,
                pressure_level="normal",
            ),
            disks=[
                DiskVolume(
                    path="/",
                    total_bytes=500_107_862_016,
                    used_bytes=245_000_000_000,
                    free_bytes=255_107_862_016,
                    percent_used=49.0,
                )
            ],
            battery=BatteryState(present=False),
            storage_devices=[
                StorageDeviceHealth(
                    device_id="nvme0n1",
                    model="Demo SSD",
                    protocol="NVMe",
                    medium="SSD",
                    health_status="Healthy",
                    operational_status="OK",
                )
            ],
        ),
        network=NetworkState(
            interfaces=[
                NetworkInterface(
                    name="eth0",
                    is_up=True,
                    mac_address="52:54:00:12:34:56",
                    addresses=[
                        InterfaceAddress(
                            family="ipv4",
                            address="192.168.1.50",
                            netmask="24",
                            is_loopback=False,
                        )
                    ],
                    mtu=1500,
                    type_hint="ethernet",
                )
            ],
            local_addresses=["192.168.1.50"],
            active_interfaces=["eth0"],
            arp_neighbors=[
                ArpNeighbor(
                    ip_address="192.168.1.1",
                    mac_address="aa:bb:cc:dd:ee:ff",
                    interface="eth0",
                    state="reachable",
                )
            ],
            route_summary=RouteSummary(
                default_gateway="192.168.1.1",
                default_interface="eth0",
                has_default_route=True,
                routes=[
                    RouteEntry(
                        destination="default",
                        gateway="192.168.1.1",
                        interface="eth0",
                        metric=100,
                    )
                ],
                default_route_state="present",
                observations=[],
            ),
        ),
        dns=DnsState(
            resolvers=["1.1.1.1", "8.8.8.8"],
            checks=[
                DnsResolutionCheck(
                    hostname="github.com",
                    success=True,
                    resolved_addresses=["140.82.113.3"],
                    duration_ms=12,
                ),
                DnsResolutionCheck(
                    hostname="python.org",
                    success=True,
                    resolved_addresses=["151.101.64.223"],
                    duration_ms=14,
                ),
            ],
        ),
        connectivity=ConnectivityState(
            internet_reachable=True,
            tcp_checks=[
                TcpConnectivityCheck(
                    target=DEFAULT_TCP_TARGETS[0],
                    success=True,
                    latency_ms=28.1,
                    ip_used="140.82.113.3",
                    duration_ms=28,
                ),
                TcpConnectivityCheck(
                    target=DEFAULT_TCP_TARGETS[1],
                    success=True,
                    latency_ms=14.2,
                    ip_used="1.1.1.1",
                    duration_ms=14,
                ),
            ],
            ping_checks=[],
            trace_results=[],
        ),
        vpn=VpnState(),
        services=ServiceState(
            checks=[
                ServiceCheck(
                    target=DEFAULT_TCP_TARGETS[0],
                    success=True,
                    latency_ms=30.0,
                    duration_ms=30,
                ),
                ServiceCheck(
                    target=DEFAULT_TCP_TARGETS[1],
                    success=True,
                    latency_ms=16.0,
                    duration_ms=16,
                ),
            ]
        ),
    )
    return _finalize_result(
        facts=facts,
        options=options,
        warnings=[],
        generated_at="2026-04-01T00:00:00+00:00",
        elapsed_ms=182,
        platform=PlatformInfo(
            system="Linux",
            release="6.8.0",
            version="demo-build",
            machine="x86_64",
            python_version="3.13.4",
        ),
        durations_ms={
            "host": 4,
            "resources": 18,
            "storage": 7,
            "network": 12,
            "routing": 9,
            "dns": 26,
            "connectivity": 43,
            "vpn": 2,
            "services": 27,
        },
    )


def build_profile_dns_issue_result() -> EndpointDiagnosticResult:
    profile = get_profile("dns-issue")
    options = DiagnosticsRunOptions(
        selected_checks=list(profile.recommended_checks),
        targets=list(profile.tcp_targets),
        dns_hosts=list(profile.dns_hosts),
        profile=profile,
    )
    facts = CollectedFacts(
        host=HostBasics(
            hostname="field-macbook",
            operating_system="Darwin",
            kernel="24.0.0",
            current_user="operator",
            uptime_seconds=9200,
        ),
        resources=ResourceState(
            cpu=CpuState(logical_cpus=None),
            memory=MemoryState(
                total_bytes=None,
                available_bytes=None,
                free_bytes=None,
                pressure_level=None,
            ),
            disks=[],
        ),
        network=NetworkState(
            interfaces=[
                NetworkInterface(
                    name="en0",
                    is_up=True,
                    mac_address="aa:bb:cc:dd:ee:ff",
                    addresses=[
                        InterfaceAddress(
                            family="ipv4",
                            address="192.168.0.25",
                            netmask="24",
                            is_loopback=False,
                        )
                    ],
                    mtu=1500,
                    type_hint="ethernet",
                )
            ],
            local_addresses=["192.168.0.25"],
            active_interfaces=["en0"],
            arp_neighbors=[],
            route_summary=RouteSummary(
                default_gateway="192.168.0.1",
                default_interface="en0",
                has_default_route=True,
                routes=[
                    RouteEntry(
                        destination="default",
                        gateway="192.168.0.1",
                        interface="en0",
                        metric=None,
                    )
                ],
                default_route_state="present",
                observations=[],
            ),
        ),
        dns=DnsState(
            resolvers=["192.168.0.1"],
            checks=[
                DnsResolutionCheck(
                    hostname="github.com",
                    success=False,
                    error="temporary failure in name resolution",
                    duration_ms=10,
                ),
                DnsResolutionCheck(
                    hostname="python.org",
                    success=False,
                    error="temporary failure in name resolution",
                    duration_ms=11,
                ),
                DnsResolutionCheck(
                    hostname="pypi.org",
                    success=False,
                    error="temporary failure in name resolution",
                    duration_ms=12,
                ),
            ],
        ),
        connectivity=ConnectivityState(
            internet_reachable=True,
            tcp_checks=[
                TcpConnectivityCheck(
                    target=profile.tcp_targets[0],
                    success=True,
                    latency_ms=14.2,
                    ip_used="1.1.1.1",
                    duration_ms=14,
                ),
                TcpConnectivityCheck(
                    target=profile.tcp_targets[1],
                    success=True,
                    latency_ms=15.1,
                    ip_used="8.8.8.8",
                    duration_ms=15,
                ),
            ],
            ping_checks=[],
            trace_results=[],
        ),
        vpn=VpnState(),
        services=ServiceState(),
    )
    return _finalize_result(
        facts=facts,
        options=options,
        warnings=[],
        generated_at="2026-04-01T00:05:00+00:00",
        elapsed_ms=201,
        platform=PlatformInfo(
            system="macOS",
            release="15.0",
            version="demo-build",
            machine="arm64",
            python_version="3.13.4",
        ),
        durations_ms={
            "host": 4,
            "network": 13,
            "routing": 7,
            "dns": 38,
            "connectivity": 34,
        },
    )


def build_degraded_partial_result() -> EndpointDiagnosticResult:
    targets = [
        TcpTarget(host="github.com", port=443, label="github-https"),
        TcpTarget(host="1.1.1.1", port=53, label="cloudflare-dns"),
    ]
    options = DiagnosticsRunOptions(
        selected_checks=["network", "routing", "dns", "connectivity", "vpn"],
        targets=targets,
        dns_hosts=["github.com", "python.org"],
        enable_trace=True,
    )
    warnings = [
        DiagnosticWarning(
            domain="routing",
            code="route-data-warning",
            message=(
                "Default route was collected, but it appears link-scoped and may be incomplete."
            ),
        ),
        DiagnosticWarning(
            domain="connectivity",
            code="trace-unavailable",
            message="Traceroute command is unavailable on this endpoint.",
        ),
    ]
    facts = CollectedFacts(
        host=HostBasics(
            hostname="branch-office-laptop",
            operating_system="Linux",
            kernel="6.8.0",
            current_user="operator",
            uptime_seconds=5400,
        ),
        resources=ResourceState(
            cpu=CpuState(logical_cpus=None),
            memory=MemoryState(
                total_bytes=None,
                available_bytes=None,
                free_bytes=None,
                pressure_level=None,
            ),
            disks=[],
        ),
        network=NetworkState(
            interfaces=[
                NetworkInterface(
                    name="eth0",
                    is_up=True,
                    mac_address="52:54:00:12:34:56",
                    addresses=[
                        InterfaceAddress(
                            family="ipv4",
                            address="192.168.50.24",
                            netmask="24",
                            is_loopback=False,
                        )
                    ],
                    mtu=1500,
                    type_hint="ethernet",
                ),
                NetworkInterface(
                    name="tun0",
                    is_up=False,
                    mac_address=None,
                    addresses=[],
                    mtu=1380,
                    type_hint="tunnel",
                ),
            ],
            local_addresses=["192.168.50.24"],
            active_interfaces=["eth0"],
            arp_neighbors=[],
            route_summary=RouteSummary(
                default_gateway="link#15",
                default_interface="tun0",
                has_default_route=True,
                routes=[
                    RouteEntry(
                        destination="default",
                        gateway="link#15",
                        interface="tun0",
                        metric=50,
                        note=(
                            "Default route uses link-scoped gateway link#15, "
                            "so next-hop reachability is less explicit."
                        ),
                    )
                ],
                default_route_state="suspect",
                observations=[
                    (
                        "Default route uses link-scoped gateway link#15, so "
                        "next-hop reachability is less explicit."
                    )
                ],
            ),
        ),
        dns=DnsState(
            resolvers=["10.0.0.53"],
            checks=[
                DnsResolutionCheck(
                    hostname="github.com",
                    success=True,
                    resolved_addresses=["140.82.114.3"],
                    duration_ms=12,
                ),
                DnsResolutionCheck(
                    hostname="python.org",
                    success=False,
                    error="temporary failure in name resolution",
                    duration_ms=15,
                ),
            ],
        ),
        connectivity=ConnectivityState(
            internet_reachable=False,
            tcp_checks=[
                TcpConnectivityCheck(
                    target=targets[0],
                    success=False,
                    error="timeout",
                    duration_ms=3000,
                ),
                TcpConnectivityCheck(
                    target=targets[1],
                    success=False,
                    error="timeout",
                    duration_ms=3000,
                ),
            ],
            ping_checks=[],
            trace_results=[
                TraceResult(
                    target="github.com",
                    ran=False,
                    success=False,
                    error="trace-command-unavailable",
                    duration_ms=1,
                ),
                TraceResult(
                    target="1.1.1.1",
                    ran=False,
                    success=False,
                    error="trace-command-unavailable",
                    duration_ms=1,
                ),
            ],
        ),
        vpn=VpnState(),
        services=ServiceState(),
    )
    result = _finalize_result(
        facts=facts,
        options=options,
        warnings=warnings,
        generated_at="2026-04-01T00:10:00+00:00",
        elapsed_ms=175,
        platform=PlatformInfo(
            system="Linux",
            release="6.8.0",
            version="demo-build",
            machine="x86_64",
            python_version="3.13.4",
        ),
        durations_ms={
            "host": 4,
            "network": 10,
            "routing": 9,
            "dns": 30,
            "connectivity": 61,
            "vpn": 2,
        },
    )
    result.raw_command_capture = [
        RawCommandCapture(
            command=["ip", "route", "show"],
            returncode=0,
            stdout="default dev tun0 scope link\n",
            stderr="",
            duration_ms=5,
        )
    ]
    return result


def build_profile_vpn_issue_result() -> EndpointDiagnosticResult:
    profile = get_profile("vpn-issue")
    options = DiagnosticsRunOptions(
        selected_checks=list(profile.recommended_checks),
        targets=list(profile.tcp_targets),
        dns_hosts=list(profile.dns_hosts),
        profile=profile,
    )
    facts = CollectedFacts(
        host=HostBasics(
            hostname="remote-windows-laptop",
            operating_system="Windows",
            kernel="10.0.22631",
            current_user="operator",
            uptime_seconds=7200,
        ),
        resources=ResourceState(
            cpu=CpuState(logical_cpus=8, utilization_percent_estimate=11.4),
            memory=MemoryState(
                total_bytes=16 * 1024**3,
                available_bytes=9_000_000_000,
                free_bytes=7_300_000_000,
                pressure_level="normal",
            ),
            disks=[],
            battery=BatteryState(present=True, charge_percent=78, status="charging"),
        ),
        network=NetworkState(
            interfaces=[
                NetworkInterface(
                    name="Wi-Fi",
                    is_up=True,
                    mac_address="00:11:22:33:44:55",
                    addresses=[
                        InterfaceAddress(
                            family="ipv4",
                            address="192.168.10.42",
                            netmask="24",
                            is_loopback=False,
                        )
                    ],
                    mtu=1500,
                    type_hint="wireless",
                ),
                NetworkInterface(
                    name="utun2",
                    is_up=True,
                    mac_address=None,
                    addresses=[
                        InterfaceAddress(
                            family="ipv4",
                            address="10.8.0.14",
                            netmask="24",
                            is_loopback=False,
                        )
                    ],
                    mtu=1380,
                    type_hint="tunnel",
                ),
            ],
            local_addresses=["192.168.10.42", "10.8.0.14"],
            active_interfaces=["Wi-Fi", "utun2"],
            arp_neighbors=[],
            route_summary=RouteSummary(
                default_gateway="10.8.0.1",
                default_interface="utun2",
                has_default_route=True,
                routes=[
                    RouteEntry(
                        destination="default",
                        gateway="10.8.0.1",
                        interface="utun2",
                        metric=25,
                    )
                ],
                default_route_state="present",
                observations=[],
            ),
        ),
        dns=DnsState(
            resolvers=["10.8.0.2"],
            checks=[
                DnsResolutionCheck(
                    hostname="github.com",
                    success=True,
                    resolved_addresses=["140.82.112.3"],
                    duration_ms=11,
                )
            ],
        ),
        connectivity=ConnectivityState(
            internet_reachable=True,
            tcp_checks=[
                TcpConnectivityCheck(
                    target=profile.tcp_targets[0],
                    success=True,
                    latency_ms=24.3,
                    ip_used="140.82.112.3",
                    duration_ms=24,
                ),
                TcpConnectivityCheck(
                    target=profile.tcp_targets[1],
                    success=False,
                    error="timeout",
                    duration_ms=3000,
                ),
            ],
            ping_checks=[],
            trace_results=[],
        ),
        vpn=VpnState(
            signals=[
                VpnSignal(
                    interface_name="utun2",
                    signal_type="interface-name-and-address-heuristic",
                    description="Tunnel-like interface name detected with a usable address.",
                    active=True,
                    confidence=0.82,
                    address_count=1,
                ),
                VpnSignal(
                    interface_name="utun2",
                    signal_type="default-route-heuristic",
                    description="Default route uses an interface that looks like a VPN or tunnel.",
                    active=True,
                    confidence=0.9,
                    address_count=1,
                ),
            ]
        ),
        services=ServiceState(
            checks=[
                ServiceCheck(
                    target=profile.tcp_targets[0],
                    success=True,
                    latency_ms=26.0,
                    duration_ms=26,
                ),
                ServiceCheck(
                    target=profile.tcp_targets[1],
                    success=False,
                    error="timeout",
                    duration_ms=3000,
                ),
            ]
        ),
    )
    return _finalize_result(
        facts=facts,
        options=options,
        warnings=[],
        generated_at="2026-04-01T00:12:00+00:00",
        elapsed_ms=188,
        platform=PlatformInfo(
            system="Windows",
            release="11",
            version="demo-build",
            machine="AMD64",
            python_version="3.13.4",
        ),
        durations_ms={
            "host": 4,
            "network": 12,
            "routing": 8,
            "dns": 18,
            "connectivity": 44,
            "vpn": 2,
            "services": 29,
        },
    )


def _finalize_result(
    *,
    facts: CollectedFacts,
    options: DiagnosticsRunOptions,
    warnings: list[DiagnosticWarning],
    generated_at: str,
    elapsed_ms: int,
    platform: PlatformInfo,
    durations_ms: dict[str, int],
) -> EndpointDiagnosticResult:
    findings, probable_fault_domain = evaluate_selected_findings(facts, options.selected_checks)
    findings = enrich_findings(findings)
    execution = build_execution_records(facts, options, warnings, durations_ms)
    guided_experience = build_guided_experience(findings, execution, options.profile)
    return EndpointDiagnosticResult(
        metadata=Metadata(
            project_name="occams-beard",
            version="0.1.0",
            generated_at=generated_at,
            elapsed_ms=elapsed_ms,
            selected_checks=list(options.selected_checks),
            profile_id=options.profile.profile_id if options.profile else None,
            profile_name=options.profile.name if options.profile else None,
            issue_category=options.profile.issue_category if options.profile else None,
        ),
        platform=platform,
        facts=facts,
        findings=findings,
        probable_fault_domain=cast(FaultDomain, probable_fault_domain),
        warnings=list(warnings),
        execution=execution,
        guided_experience=guided_experience,
    )
