"""Human-readable report rendering."""

from __future__ import annotations

from endpoint_diagnostics_lab.models import EndpointDiagnosticResult


def render_report(result: EndpointDiagnosticResult, json_path: str | None = None) -> str:
    """Render a concise human-readable diagnostic report."""

    host = result.facts.host
    resources = result.facts.resources
    network = result.facts.network
    lines = [
        "Endpoint Diagnostics Lab Report",
        "================================",
        "",
        "Summary",
        f"- Host: {host.hostname}",
        f"- Platform: {result.platform.system} {result.platform.release} ({result.platform.machine})",
        f"- Internet reachable: {'yes' if result.facts.connectivity.internet_reachable else 'no'}",
        f"- Default route present: {'yes' if network.route_summary.has_default_route else 'no'}",
        f"- Probable fault domain: {result.probable_fault_domain}",
        "",
        "Key Findings",
    ]

    for finding in result.findings[:5]:
        lines.append(f"- [{finding.severity.upper()}] {finding.title}: {finding.summary}")

    lines.extend(
        [
            "",
            "System Snapshot",
            f"- Current user: {host.current_user or 'unknown'}",
            f"- Uptime (seconds): {host.uptime_seconds if host.uptime_seconds is not None else 'unknown'}",
            f"- CPU logical cores: {resources.cpu.logical_cpus if resources.cpu.logical_cpus is not None else 'unknown'}",
            f"- CPU utilization estimate: {_format_percent(resources.cpu.utilization_percent_estimate)}",
            f"- Memory pressure: {resources.memory.pressure_level or 'unknown'}",
            f"- Memory available: {_format_bytes(resources.memory.available_bytes)} / {_format_bytes(resources.memory.total_bytes)}",
            "",
            "Network Snapshot",
            f"- Active interfaces: {', '.join(network.active_interfaces) if network.active_interfaces else 'none detected'}",
            f"- Local addresses: {', '.join(network.local_addresses) if network.local_addresses else 'none detected'}",
            f"- Default gateway: {network.route_summary.default_gateway or 'none'}",
            f"- Default interface: {network.route_summary.default_interface or 'none'}",
            "",
            "Connectivity Results",
        ]
    )

    for check in result.facts.connectivity.tcp_checks:
        state = "reachable" if check.success else f"failed ({check.error or 'unknown-error'})"
        latency = f", {check.latency_ms:.1f} ms" if check.latency_ms is not None else ""
        lines.append(f"- TCP {check.target.host}:{check.target.port}: {state}{latency}")

    if result.facts.dns.checks:
        for check in result.facts.dns.checks:
            detail = ", ".join(check.resolved_addresses) if check.success else check.error or "failed"
            lines.append(f"- DNS {check.hostname}: {detail}")

    lines.extend(
        [
            "",
            "Probable Fault Domain",
            f"- {result.probable_fault_domain}",
        ]
    )

    if json_path:
        lines.extend(["", f"Raw-data file path: {json_path}"])

    if result.warnings:
        lines.extend(["", "Warnings"])
        for warning in result.warnings:
            lines.append(f"- [{warning.domain}] {warning.message}")

    return "\n".join(lines)


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    suffixes = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    for suffix in suffixes:
        if size < 1024 or suffix == suffixes[-1]:
            return f"{size:.1f} {suffix}"
        size /= 1024
    return f"{value} B"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f}%"
