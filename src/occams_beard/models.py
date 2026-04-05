"""Normalized data models for host and network diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["info", "low", "medium", "high"]
ExecutionStatus = Literal["passed", "failed", "partial", "unsupported", "skipped", "not_run"]
FaultDomain = Literal[
    "healthy",
    "local_host",
    "local_network",
    "dns",
    "internet_edge",
    "vpn",
    "upstream_network",
    "unknown",
]
RedactionLevel = Literal["none", "safe", "strict"]


@dataclass(slots=True)
class DiagnosticWarning:
    """Represents a non-fatal limitation or degraded check."""

    domain: str
    code: str
    message: str


@dataclass(slots=True)
class Metadata:
    """Metadata captured for a single diagnostics execution."""

    project_name: str
    version: str
    generated_at: str
    elapsed_ms: int
    selected_checks: list[str]
    profile_id: str | None = None
    profile_name: str | None = None
    issue_category: str | None = None
    intake_debug: dict[str, Any] | None = None


@dataclass(slots=True)
class PlatformInfo:
    """Basic platform information for the current endpoint."""

    system: str
    release: str
    version: str
    machine: str
    python_version: str


@dataclass(slots=True)
class HostBasics:
    """Core host-level facts."""

    hostname: str
    operating_system: str
    kernel: str
    current_user: str | None
    uptime_seconds: int | None


@dataclass(slots=True)
class ClockSkewCheck:
    """Bounded external clock-reference comparison for the local endpoint."""

    status: str
    reference_kind: str
    reference_label: str
    reference_url: str | None = None
    reference_time_iso: str | None = None
    observed_at_utc_iso: str | None = None
    skew_seconds: float | None = None
    absolute_skew_seconds: float | None = None
    duration_ms: int | None = None
    error: str | None = None


@dataclass(slots=True)
class TimeState:
    """Current local clock and timezone facts for the endpoint."""

    local_time_iso: str
    utc_time_iso: str
    timezone_name: str | None = None
    timezone_identifier: str | None = None
    timezone_identifier_source: str | None = None
    utc_offset_minutes: int | None = None
    timezone_offset_consistent: bool | None = None
    skew_check: ClockSkewCheck | None = None


@dataclass(slots=True)
class CpuState:
    """CPU-related facts."""

    logical_cpus: int | None
    load_average_1m: float | None = None
    load_average_5m: float | None = None
    load_average_15m: float | None = None
    utilization_percent_estimate: float | None = None
    load_ratio_1m: float | None = None
    saturation_level: str | None = None


@dataclass(slots=True)
class MemoryState:
    """Memory-related facts."""

    total_bytes: int | None
    available_bytes: int | None
    free_bytes: int | None
    pressure_level: str | None = None
    available_percent: float | None = None
    swap_total_bytes: int | None = None
    swap_free_bytes: int | None = None
    swap_used_bytes: int | None = None
    committed_bytes: int | None = None
    commit_limit_bytes: int | None = None
    commit_pressure_level: str | None = None


@dataclass(slots=True)
class DiskVolume:
    """Usage information for a mounted volume or filesystem."""

    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent_used: float
    free_percent: float | None = None
    pressure_level: str | None = None
    role_hint: str | None = None


@dataclass(slots=True)
class BatteryState:
    """Read-only battery health information when the endpoint exposes it."""

    present: bool
    charge_percent: int | None = None
    status: str | None = None
    cycle_count: int | None = None
    condition: str | None = None
    health_percent: float | None = None


@dataclass(slots=True)
class StorageDeviceHealth:
    """Read-only storage-device health information when the endpoint exposes it."""

    device_id: str
    model: str | None = None
    protocol: str | None = None
    medium: str | None = None
    health_status: str | None = None
    operational_status: str | None = None


@dataclass(slots=True)
class ProcessCategoryLoad:
    """A bounded, privacy-preserving summary of heavy process categories."""

    category: str
    process_count: int
    combined_cpu_percent_estimate: float | None = None
    peak_cpu_percent_estimate: float | None = None
    combined_memory_bytes: int | None = None
    peak_memory_bytes: int | None = None


@dataclass(slots=True)
class ProcessSnapshot:
    """Bounded process-load hints derived from a single local snapshot."""

    sampled_process_count: int
    high_cpu_process_count: int = 0
    high_memory_process_count: int = 0
    top_categories: list[ProcessCategoryLoad] = field(default_factory=list)


@dataclass(slots=True)
class ResourceState:
    """Normalized view of host resource state."""

    cpu: CpuState
    memory: MemoryState
    disks: list[DiskVolume] = field(default_factory=list)
    battery: BatteryState | None = None
    storage_devices: list[StorageDeviceHealth] = field(default_factory=list)
    process_snapshot: ProcessSnapshot | None = None


@dataclass(slots=True)
class InterfaceAddress:
    """An address attached to a network interface."""

    family: str
    address: str
    netmask: str | None = None
    is_loopback: bool = False


@dataclass(slots=True)
class NetworkInterface:
    """A normalized network interface record."""

    name: str
    is_up: bool
    mac_address: str | None = None
    addresses: list[InterfaceAddress] = field(default_factory=list)
    mtu: int | None = None
    type_hint: str | None = None


@dataclass(slots=True)
class RouteEntry:
    """A normalized routing table entry."""

    destination: str
    gateway: str | None
    interface: str | None
    metric: int | None = None
    note: str | None = None


@dataclass(slots=True)
class RouteSummary:
    """A compact summary of routing state."""

    default_gateway: str | None
    default_interface: str | None
    has_default_route: bool
    routes: list[RouteEntry] = field(default_factory=list)
    default_route_state: str = "missing"
    observations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ArpNeighbor:
    """A normalized ARP or neighbor-cache entry."""

    ip_address: str
    mac_address: str | None
    interface: str | None = None
    state: str | None = None


@dataclass(slots=True)
class NetworkState:
    """Collected network configuration facts."""

    interfaces: list[NetworkInterface] = field(default_factory=list)
    local_addresses: list[str] = field(default_factory=list)
    active_interfaces: list[str] = field(default_factory=list)
    arp_neighbors: list[ArpNeighbor] = field(default_factory=list)
    route_summary: RouteSummary = field(default_factory=lambda: RouteSummary(None, None, False, []))


@dataclass(slots=True)
class DnsResolutionCheck:
    """Outcome of a DNS resolution attempt."""

    hostname: str
    success: bool
    resolved_addresses: list[str] = field(default_factory=list)
    error: str | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class DnsState:
    """Collected DNS facts."""

    resolvers: list[str] = field(default_factory=list)
    checks: list[DnsResolutionCheck] = field(default_factory=list)


@dataclass(slots=True)
class TcpTarget:
    """A TCP reachability target."""

    host: str
    port: int
    label: str | None = None


@dataclass(slots=True)
class TcpConnectivityCheck:
    """Outcome of a TCP reachability test."""

    target: TcpTarget
    success: bool
    latency_ms: float | None = None
    error: str | None = None
    ip_used: str | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class PingResult:
    """Outcome of an ICMP-style reachability check."""

    target: str
    success: bool
    packet_loss_percent: float | None = None
    average_latency_ms: float | None = None
    error: str | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class TraceHop:
    """A single traceroute hop."""

    hop: int
    host: str | None
    address: str | None
    latency_ms: float | None
    note: str | None = None


@dataclass(slots=True)
class TraceResult:
    """Outcome of a traceroute or tracert execution."""

    target: str
    ran: bool
    success: bool
    hops: list[TraceHop] = field(default_factory=list)
    error: str | None = None
    partial: bool = False
    target_address: str | None = None
    last_responding_hop: int | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class ConnectivityState:
    """Generic path reachability facts for the endpoint."""

    internet_reachable: bool
    tcp_checks: list[TcpConnectivityCheck] = field(default_factory=list)
    ping_checks: list[PingResult] = field(default_factory=list)
    trace_results: list[TraceResult] = field(default_factory=list)


@dataclass(slots=True)
class VpnSignal:
    """Heuristic evidence that a tunnel or VPN may be active."""

    interface_name: str
    signal_type: str
    description: str
    active: bool
    confidence: float
    address_count: int = 0


@dataclass(slots=True)
class VpnState:
    """Collected VPN-related signals."""

    signals: list[VpnSignal] = field(default_factory=list)


@dataclass(slots=True)
class ServiceCheck:
    """Outcome of an intended endpoint or application reachability check."""

    target: TcpTarget
    success: bool
    latency_ms: float | None = None
    error: str | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class ServiceState:
    """Collected intended service reachability facts."""

    checks: list[ServiceCheck] = field(default_factory=list)


@dataclass(slots=True)
class CollectedFacts:
    """All normalized facts gathered from collectors."""

    host: HostBasics
    resources: ResourceState
    network: NetworkState
    dns: DnsState
    connectivity: ConnectivityState
    vpn: VpnState
    services: ServiceState
    time: TimeState | None = None


@dataclass(slots=True)
class Finding:
    """A deterministic finding produced from evidence."""

    identifier: str
    severity: Severity
    title: str
    summary: str
    evidence: list[str]
    probable_cause: str
    fault_domain: FaultDomain
    confidence: float
    heuristic: bool = False
    plain_language: str | None = None
    evidence_summary: str | None = None
    safe_next_actions: list[str] = field(default_factory=list)
    escalation_triggers: list[str] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ExecutionProbe:
    """Execution status for a concrete probe or sub-check."""

    probe_id: str
    label: str
    status: ExecutionStatus
    duration_ms: int | None = None
    target: str | None = None
    details: list[str] = field(default_factory=list)
    warnings: list[DiagnosticWarning] = field(default_factory=list)
    creates_network_egress: bool = False


@dataclass(slots=True)
class DomainExecution:
    """Execution status for a diagnostic domain."""

    domain: str
    label: str
    status: ExecutionStatus
    selected: bool
    duration_ms: int | None = None
    summary: str | None = None
    warnings: list[DiagnosticWarning] = field(default_factory=list)
    probes: list[ExecutionProbe] = field(default_factory=list)
    creates_network_egress: bool = False


@dataclass(slots=True)
class GuidedExperience:
    """Deterministic self-service summary derived from findings and execution state."""

    issue_category: str | None = None
    profile_id: str | None = None
    profile_name: str | None = None
    what_we_know: list[str] = field(default_factory=list)
    likely_happened: list[str] = field(default_factory=list)
    safe_next_steps: list[str] = field(default_factory=list)
    escalation_guidance: list[str] = field(default_factory=list)
    uncertainty_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RawCommandCapture:
    """Captured raw command execution for an explicitly enabled support bundle."""

    command: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    error: str | None = None


@dataclass(slots=True)
class DiagnosticProfile:
    """Local reusable scenario profile for repeatable diagnostics runs."""

    profile_id: str
    name: str
    description: str
    issue_category: str
    recommended_checks: list[str]
    dns_hosts: list[str] = field(default_factory=list)
    tcp_targets: list[TcpTarget] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    safe_user_guidance: list[str] = field(default_factory=list)
    escalation_guidance: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RedactionSummary:
    """Human-readable and machine-readable description of bundle redactions."""

    level: RedactionLevel
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SupportBundleFile:
    """Manifest entry for a file placed in a support bundle."""

    path: str
    sha256: str
    size_bytes: int


@dataclass(slots=True)
class SupportBundleManifest:
    """Structured metadata describing a support bundle export."""

    bundle_format_version: str
    generated_at: str
    app_version: str
    schema_version: str
    redaction_level: RedactionLevel
    raw_command_capture_included: bool
    selected_checks: list[str]
    profile_id: str | None = None
    issue_category: str | None = None
    files: list[SupportBundleFile] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EndpointDiagnosticResult:
    """The full diagnostic result emitted by the tool."""

    metadata: Metadata
    platform: PlatformInfo
    facts: CollectedFacts
    schema_version: str = "1.4.0"
    findings: list[Finding] = field(default_factory=list)
    probable_fault_domain: FaultDomain = "unknown"
    warnings: list[DiagnosticWarning] = field(default_factory=list)
    execution: list[DomainExecution] = field(default_factory=list)
    guided_experience: GuidedExperience | None = None
    raw_command_capture: list[RawCommandCapture] = field(default_factory=list)
