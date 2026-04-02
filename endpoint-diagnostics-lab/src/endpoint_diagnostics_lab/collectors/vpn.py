"""Collectors for heuristic VPN and tunnel detection."""

from __future__ import annotations

from endpoint_diagnostics_lab.models import NetworkState, RouteSummary, VpnSignal, VpnState


VPN_NAME_TOKENS = ("tun", "tap", "utun", "ppp", "wg", "tailscale", "zerotier", "vpn")


def collect_vpn_state(network_state: NetworkState, route_summary: RouteSummary) -> VpnState:
    """Heuristically identify active tunnel or VPN signals."""

    signals: list[VpnSignal] = []

    for interface in network_state.interfaces:
        lowered_name = interface.name.lower()
        if interface.is_up and any(token in lowered_name for token in VPN_NAME_TOKENS):
            confidence = 0.75 if interface.type_hint == "tunnel" else 0.6
            signals.append(
                VpnSignal(
                    interface_name=interface.name,
                    signal_type="interface-name-heuristic",
                    description="Active interface name matches a common VPN or tunnel pattern.",
                    active=True,
                    confidence=confidence,
                )
            )

    if route_summary.default_interface and any(
        token in route_summary.default_interface.lower() for token in VPN_NAME_TOKENS
    ):
        signals.append(
            VpnSignal(
                interface_name=route_summary.default_interface,
                signal_type="default-route-heuristic",
                description="Default route uses an interface that looks like a VPN or tunnel.",
                active=True,
                confidence=0.85,
            )
        )

    return VpnState(signals=signals)
