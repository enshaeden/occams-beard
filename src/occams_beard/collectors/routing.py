"""Collectors for routing data."""

from __future__ import annotations

from occams_beard.models import DiagnosticWarning, RouteEntry, RouteSummary
from occams_beard.platform import current_platform, linux, macos, windows
from occams_beard.utils.parsing import empty_route_data


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
        raw_data, command_result = empty_route_data(), None
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
                    "Route inventory command failed: "
                    f"{command_result.error or command_result.stderr.strip() or 'unknown-error'}"
                ),
            )
        )

    for parse_warning in raw_data["parse_warnings"]:
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
            has_default_route=raw_data["has_default_route"],
            routes=[
                RouteEntry(
                    destination=route["destination"],
                    gateway=route["gateway"],
                    interface=route["interface"],
                    metric=route["metric"],
                    note=route["note"],
                )
                for route in raw_data["routes"]
            ],
            default_route_state=raw_data["default_route_state"],
            observations=list(raw_data["observations"]),
        ),
        warnings,
    )
