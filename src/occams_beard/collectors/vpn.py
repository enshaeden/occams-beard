"""Collectors for heuristic VPN and tunnel detection."""

from __future__ import annotations

import ipaddress

from occams_beard.models import NetworkState, RouteSummary, VpnSignal, VpnState
from occams_beard.platform import current_platform

VPN_NAME_TOKENS = ("tun", "tap", "utun", "ppp", "wg", "tailscale", "zerotier", "vpn")


def collect_vpn_state(network_state: NetworkState, route_summary: RouteSummary) -> VpnState:
    """Heuristically identify active tunnel or VPN signals."""

    signals: list[VpnSignal] = []
    platform_name = current_platform()
    interface_address_counts = {
        interface.name: sum(
            1
            for address in interface.addresses
            if not address.is_loopback and _address_is_usable(address.address)
        )
        for interface in network_state.interfaces
    }
    route_owned_interfaces = {
        route.interface
        for route in route_summary.routes
        if route.interface
        and route.destination != "default"
        and route.gateway not in {None, "link#0"}
    }

    for interface in network_state.interfaces:
        lowered_name = interface.name.lower()
        if not interface.is_up or not any(token in lowered_name for token in VPN_NAME_TOKENS):
            continue

        address_count = interface_address_counts.get(interface.name, 0)
        signal = _build_vpn_signal(
            interface_name=interface.name,
            lowered_name=lowered_name,
            type_hint=interface.type_hint,
            platform_name=platform_name,
            address_count=address_count,
            is_default_route_interface=route_summary.default_interface == interface.name,
            owns_non_default_routes=interface.name in route_owned_interfaces,
        )
        if signal is not None:
            signals.append(signal)

    return VpnState(signals=signals)


def _build_vpn_signal(
    *,
    interface_name: str,
    lowered_name: str,
    type_hint: str | None,
    platform_name: str,
    address_count: int,
    is_default_route_interface: bool,
    owns_non_default_routes: bool,
) -> VpnSignal | None:
    is_macos_utun = platform_name == "macos" and lowered_name.startswith("utun")
    if is_default_route_interface:
        return VpnSignal(
            interface_name=interface_name,
            signal_type="default-route-tunnel-heuristic",
            description=(
                "Default route uses a tunnel-like interface with a usable address."
                if address_count
                else "Default route uses a tunnel-like interface."
            ),
            active=True,
            confidence=0.93 if address_count else 0.84,
            address_count=address_count,
        )
    if owns_non_default_routes and address_count:
        return VpnSignal(
            interface_name=interface_name,
            signal_type="route-owned-tunnel-heuristic",
            description=(
                "Tunnel-like interface owns non-default routes and has a usable address."
            ),
            active=True,
            confidence=0.79 if type_hint == "tunnel" else 0.72,
            address_count=address_count,
        )
    if address_count:
        return VpnSignal(
            interface_name=interface_name,
            signal_type=(
                "tunnel-interface-present"
                if is_macos_utun
                else "interface-name-and-address-heuristic"
            ),
            description=(
                "Tunnel-like interface is present with a usable address, but routing does not "
                "yet show meaningful VPN ownership."
                if is_macos_utun
                else "Active interface name matches a common VPN or tunnel pattern and has a "
                "usable address."
            ),
            active=True,
            confidence=0.45 if is_macos_utun else (0.82 if type_hint == "tunnel" else 0.74),
            address_count=address_count,
        )
    if is_macos_utun:
        return None
    return VpnSignal(
        interface_name=interface_name,
        signal_type="interface-name-heuristic",
        description=(
            "Active interface name matches a common VPN or tunnel pattern, but no usable "
            "address was collected."
        ),
        active=True,
        confidence=0.55,
        address_count=0,
    )


def _address_is_usable(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return not (parsed.is_loopback or parsed.is_link_local)
