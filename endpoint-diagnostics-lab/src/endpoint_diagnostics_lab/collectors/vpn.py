"""Collectors for heuristic VPN and tunnel detection."""

from __future__ import annotations

from endpoint_diagnostics_lab.models import NetworkState, RouteSummary, VpnSignal, VpnState


VPN_NAME_TOKENS = ("tun", "tap", "utun", "ppp", "wg", "tailscale", "zerotier", "vpn")


def collect_vpn_state(network_state: NetworkState, route_summary: RouteSummary) -> VpnState:
    """Heuristically identify active tunnel or VPN signals."""

    signals: list[VpnSignal] = []
    interface_address_counts = {
        interface.name: sum(1 for address in interface.addresses if not address.is_loopback)
        for interface in network_state.interfaces
    }

    for interface in network_state.interfaces:
        lowered_name = interface.name.lower()
        if interface.is_up and any(token in lowered_name for token in VPN_NAME_TOKENS):
            address_count = interface_address_counts.get(interface.name, 0)
            signal_type = (
                "interface-name-and-address-heuristic"
                if address_count
                else "interface-name-heuristic"
            )
            confidence = 0.82 if interface.type_hint == "tunnel" and address_count else 0.68
            if interface.type_hint != "tunnel" and address_count:
                confidence = 0.74
            signals.append(
                VpnSignal(
                    interface_name=interface.name,
                    signal_type=signal_type,
                    description=(
                        "Active interface name matches a common VPN or tunnel pattern and has a usable address."
                        if address_count
                        else "Active interface name matches a common VPN or tunnel pattern, but no usable address was collected."
                    ),
                    active=True,
                    confidence=confidence,
                    address_count=address_count,
                )
            )

    if route_summary.default_interface and any(
        token in route_summary.default_interface.lower() for token in VPN_NAME_TOKENS
    ):
        address_count = interface_address_counts.get(route_summary.default_interface, 0)
        signals.append(
            VpnSignal(
                interface_name=route_summary.default_interface,
                signal_type="default-route-heuristic",
                description=(
                    "Default route uses an interface that looks like a VPN or tunnel."
                    if not address_count
                    else "Default route uses an interface that looks like a VPN or tunnel and that interface has a usable address."
                ),
                active=True,
                confidence=0.9 if address_count else 0.8,
                address_count=address_count,
            )
        )

    return VpnState(signals=signals)
