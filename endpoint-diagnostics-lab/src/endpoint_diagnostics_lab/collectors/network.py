"""Collectors for interface inventory and local addressing."""

from __future__ import annotations

import logging

from endpoint_diagnostics_lab.models import (
    DiagnosticWarning,
    InterfaceAddress,
    NetworkInterface,
    NetworkState,
)
from endpoint_diagnostics_lab.platform import current_platform
from endpoint_diagnostics_lab.platform import linux, macos, windows
from endpoint_diagnostics_lab.utils.validation import dedupe_preserve_order


LOGGER = logging.getLogger(__name__)


def collect_network_state() -> tuple[NetworkState, list[DiagnosticWarning]]:
    """Collect interface inventory and local addresses."""

    warnings: list[DiagnosticWarning] = []
    platform_name = current_platform()

    if platform_name == "linux":
        raw_interfaces, command_result = linux.read_interfaces()
    elif platform_name == "macos":
        raw_interfaces, command_result = macos.read_interfaces()
    elif platform_name == "windows":
        raw_interfaces, command_result = windows.read_interfaces()
    else:
        raw_interfaces, command_result = [], None
        warnings.append(
            DiagnosticWarning(
                domain="network",
                code="unsupported-platform",
                message=f"Network collection is unsupported on platform: {platform_name}",
            )
        )

    if command_result is not None and not command_result.succeeded:
        warnings.append(
            DiagnosticWarning(
                domain="network",
                code="interface-command-failed",
                message=(
                    f"Interface inventory command failed: {command_result.error or command_result.stderr.strip() or 'unknown-error'}"
                ),
            )
        )

    interfaces = [_normalize_interface(item) for item in raw_interfaces]
    local_addresses = dedupe_preserve_order(
        address.address
        for interface in interfaces
        for address in interface.addresses
        if not address.is_loopback
    )
    active_interfaces = [interface.name for interface in interfaces if interface.is_up]
    return (
        NetworkState(
            interfaces=interfaces,
            local_addresses=local_addresses,
            active_interfaces=active_interfaces,
        ),
        warnings,
    )


def _normalize_interface(raw_item: dict[str, object]) -> NetworkInterface:
    addresses = [
        InterfaceAddress(
            family=str(address.get("family")),
            address=str(address.get("address")),
            netmask=str(address.get("netmask")) if address.get("netmask") else None,
            is_loopback=bool(address.get("is_loopback", False)),
        )
        for address in raw_item.get("addresses", [])
    ]
    return NetworkInterface(
        name=str(raw_item.get("name")),
        is_up=bool(raw_item.get("is_up", False)),
        mac_address=str(raw_item.get("mac_address")) if raw_item.get("mac_address") else None,
        addresses=addresses,
        mtu=int(raw_item["mtu"]) if raw_item.get("mtu") is not None else None,
        type_hint=_infer_interface_type(str(raw_item.get("name"))),
    )


def _infer_interface_type(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith(("lo", "loopback")):
        return "loopback"
    if any(token in lowered for token in ("wi-fi", "wifi", "wlan", "wl")):
        return "wireless"
    if any(token in lowered for token in ("eth", "en", "ethernet")):
        return "ethernet"
    if any(token in lowered for token in ("tun", "tap", "utun", "ppp", "wg", "vpn")):
        return "tunnel"
    return "unknown"
