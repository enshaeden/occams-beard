"""Collectors for routing data."""

from __future__ import annotations

from endpoint_diagnostics_lab.models import DiagnosticWarning, RouteEntry, RouteSummary
from endpoint_diagnostics_lab.platform import current_platform
from endpoint_diagnostics_lab.platform import linux, macos, windows


def collect_route_summary() -> tuple[RouteSummary, list[DiagnosticWarning]]:
    """Collect routing and default gateway facts."""

    warnings: list[DiagnosticWarning] = []
    platform_name = current_platform()

    if platform_name == "linux":
        raw_data, command_result = linux.read_routes()
    elif platform_name == "macos":
        raw_data, command_result = macos.read_routes()
    elif platform_name == "windows":
        raw_data, command_result = windows.read_routes()
    else:
        raw_data, command_result = {
            "default_gateway": None,
            "default_interface": None,
            "has_default_route": False,
            "routes": [],
            "default_route_state": "missing",
            "observations": [],
            "parse_warnings": [],
        }, None
        warnings.append(
            DiagnosticWarning(
                domain="routing",
                code="unsupported-platform",
                message=f"Routing collection is unsupported on platform: {platform_name}",
            )
        )

    if command_result is not None and not command_result.succeeded:
        warnings.append(
            DiagnosticWarning(
                domain="routing",
                code="route-command-failed",
                message=(
                    f"Route inventory command failed: {command_result.error or command_result.stderr.strip() or 'unknown-error'}"
                ),
            )
        )

    for parse_warning in raw_data.get("parse_warnings", []):
        warnings.append(
            DiagnosticWarning(
                domain="routing",
                code="route-data-warning",
                message=str(parse_warning),
            )
        )

    return (
        RouteSummary(
            default_gateway=raw_data["default_gateway"],
            default_interface=raw_data["default_interface"],
            has_default_route=bool(raw_data["has_default_route"]),
            routes=[
                RouteEntry(
                    destination=str(route.get("destination")),
                    gateway=str(route.get("gateway")) if route.get("gateway") else None,
                    interface=str(route.get("interface")) if route.get("interface") else None,
                    metric=int(route["metric"]) if route.get("metric") is not None else None,
                    note=str(route.get("note")) if route.get("note") else None,
                )
                for route in raw_data["routes"]
            ],
            default_route_state=str(raw_data.get("default_route_state", "missing")),
            observations=[str(item) for item in raw_data.get("observations", [])],
        ),
        warnings,
    )
