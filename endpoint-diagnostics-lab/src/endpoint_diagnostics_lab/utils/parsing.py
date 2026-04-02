"""Parsing helpers for common system command outputs."""

from __future__ import annotations

import re


def parse_linux_ip_route(output: str) -> dict[str, object]:
    """Parse `ip route show` output into a compact structure."""

    default_routes: list[dict[str, object]] = []
    routes: list[dict[str, object]] = []
    observations: list[str] = []
    parse_warnings: list[str] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        route_note, normalized_line = _extract_linux_route_qualifier(line)
        tokens = normalized_line.split()
        if not tokens:
            parse_warnings.append("Ignored a malformed Linux route line with no tokens.")
            continue

        destination = tokens[0]
        gateway_match = re.search(r"\bvia\s+(\S+)", normalized_line)
        interface_match = re.search(r"\bdev\s+(\S+)", normalized_line)
        gateway = gateway_match.group(1) if gateway_match else None
        interface = interface_match.group(1) if interface_match else None
        metric = _extract_metric(normalized_line)
        destination_label = "default" if destination == "default" else destination
        note = route_note or _default_route_note(gateway, interface) if destination_label == "default" else route_note
        route = {
            "destination": destination_label,
            "gateway": gateway,
            "interface": interface,
            "metric": metric,
            "note": note,
        }
        routes.append(route)
        if destination_label == "default":
            default_routes.append(route)

    selected_default = _select_default_route(default_routes)
    default_gateway = selected_default.get("gateway") if selected_default else None
    default_interface = selected_default.get("interface") if selected_default else None
    if len(default_routes) > 1:
        observations.append(
            "Multiple default routes were collected; the summary prefers the most specific usable entry with the lowest metric."
        )
    for route in default_routes:
        if isinstance(route.get("note"), str):
            observations.append(str(route["note"]))
    if selected_default and not observations:
        observations.append(
            f"Default route summary selected interface {selected_default.get('interface') or 'unknown'}."
        )

    return {
        "default_gateway": default_gateway,
        "default_interface": default_interface,
        "has_default_route": bool(default_routes),
        "routes": routes,
        "default_route_state": _default_route_state(bool(default_routes), observations),
        "observations": _dedupe_messages(observations),
        "parse_warnings": _dedupe_messages(parse_warnings),
    }


def parse_route_get_default(output: str) -> dict[str, object]:
    """Parse macOS `route -n get default` output."""

    gateway_match = re.search(r"^\s*gateway:\s+(\S+)", output, re.MULTILINE)
    interface_match = re.search(r"^\s*interface:\s+(\S+)", output, re.MULTILINE)
    gateway = gateway_match.group(1) if gateway_match else None
    interface = interface_match.group(1) if interface_match else None

    observations: list[str] = []
    routes = []
    if gateway or interface:
        note = _default_route_note(gateway, interface)
        if note:
            observations.append(note)
        routes.append(
            {
                "destination": "default",
                "gateway": gateway,
                "interface": interface,
                "metric": None,
                "note": note,
            }
        )

    return {
        "default_gateway": gateway,
        "default_interface": interface,
        "has_default_route": gateway is not None or interface is not None,
        "routes": routes,
        "default_route_state": _default_route_state(bool(routes), observations),
        "observations": observations,
        "parse_warnings": [],
    }


def parse_route_print(output: str) -> dict[str, object]:
    """Parse Windows `route print` output into a compact structure."""

    default_routes: list[dict[str, object]] = []
    routes: list[dict[str, object]] = []
    observations: list[str] = []
    parse_warnings: list[str] = []
    in_ipv4_table = False
    in_active_routes = False

    for raw_line in output.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.startswith("IPv4 Route Table"):
            in_ipv4_table = True
            in_active_routes = False
            continue
        if stripped.startswith("IPv6 Route Table"):
            if in_ipv4_table:
                break
            continue
        if not in_ipv4_table:
            continue
        if stripped.startswith("Active Routes:"):
            in_active_routes = True
            continue
        if stripped.startswith("Persistent Routes:"):
            in_active_routes = False
            continue
        if not in_active_routes or stripped.startswith("Network Destination"):
            continue
        if not re.match(r"^\d+\.\d+\.\d+\.\d+", stripped):
            continue

        parts = stripped.split()
        if len(parts) < 5:
            parse_warnings.append(f"Ignored a malformed Windows route line: {stripped}")
            continue
        destination, netmask, gateway, interface, metric_text = parts[:5]
        destination_label = "default" if destination == "0.0.0.0" and netmask == "0.0.0.0" else destination
        metric = int(metric_text) if metric_text.isdigit() else None
        note = _default_route_note(gateway, interface) if destination_label == "default" else None
        route = {
            "destination": destination_label,
            "gateway": gateway,
            "interface": interface,
            "metric": metric,
            "note": note,
        }
        routes.append(route)
        if destination_label == "default":
            default_routes.append(route)

    selected_default = _select_default_route(default_routes)
    default_gateway = selected_default.get("gateway") if selected_default else None
    default_interface = selected_default.get("interface") if selected_default else None
    if len(default_routes) > 1:
        observations.append(
            "Multiple Windows default routes were collected; the summary prefers the most specific usable entry with the lowest metric."
        )
    for route in default_routes:
        if isinstance(route.get("note"), str):
            observations.append(str(route["note"]))

    return {
        "default_gateway": default_gateway,
        "default_interface": default_interface,
        "has_default_route": bool(default_routes),
        "routes": routes,
        "default_route_state": _default_route_state(bool(default_routes), observations),
        "observations": _dedupe_messages(observations),
        "parse_warnings": _dedupe_messages(parse_warnings),
    }


def parse_netstat_rn(output: str) -> dict[str, object]:
    """Parse Unix `netstat -rn` output."""

    default_routes: list[dict[str, object]] = []
    routes: list[dict[str, object]] = []
    observations: list[str] = []
    parse_warnings: list[str] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("Routing", "Destination", "Internet:", "Kernel")):
            continue
        parts = line.split()
        if len(parts) < 4:
            parse_warnings.append(f"Ignored a malformed netstat route line: {line}")
            continue
        destination = parts[0]
        gateway = parts[1]
        interface = parts[-1]
        metric = None
        if destination in {"default", "0.0.0.0"}:
            destination = "default"
        note = _default_route_note(gateway, interface) if destination == "default" else None
        route = {
            "destination": destination,
            "gateway": gateway,
            "interface": interface,
            "metric": metric,
            "note": note,
        }
        routes.append(route)
        if destination == "default":
            default_routes.append(route)

    selected_default = _select_default_route(default_routes)
    default_gateway = selected_default.get("gateway") if selected_default else None
    default_interface = selected_default.get("interface") if selected_default else None
    if len(default_routes) > 1:
        observations.append(
            "Multiple default routes were collected from netstat; the summary prefers the most specific usable entry."
        )
    for route in default_routes:
        if isinstance(route.get("note"), str):
            observations.append(str(route["note"]))

    return {
        "default_gateway": default_gateway,
        "default_interface": default_interface,
        "has_default_route": bool(default_routes),
        "routes": routes,
        "default_route_state": _default_route_state(bool(default_routes), observations),
        "observations": _dedupe_messages(observations),
        "parse_warnings": _dedupe_messages(parse_warnings),
    }


def parse_ip_addr_show(output: str) -> list[dict[str, object]]:
    """Parse Linux `ip addr show` output."""

    interfaces: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in output.splitlines():
        if re.match(r"^\d+:\s", raw_line):
            if current:
                interfaces.append(current)
            match = re.match(r"^\d+:\s+([^:]+):\s+<([^>]*)>.*mtu\s+(\d+)", raw_line)
            if not match:
                continue
            flags = {flag.strip() for flag in match.group(2).split(",") if flag.strip()}
            current = {
                "name": match.group(1).split("@", 1)[0],
                "is_up": "UP" in flags,
                "mtu": int(match.group(3)),
                "mac_address": None,
                "addresses": [],
            }
            continue

        if current is None:
            continue

        stripped = raw_line.strip()
        if stripped.startswith("link/ether "):
            parts = stripped.split()
            if len(parts) >= 2:
                current["mac_address"] = parts[1]
        elif stripped.startswith("inet "):
            parts = stripped.split()
            cidr = parts[1]
            address, _, prefix = cidr.partition("/")
            current["addresses"].append(
                {
                    "family": "ipv4",
                    "address": address,
                    "netmask": prefix or None,
                    "is_loopback": address.startswith("127."),
                }
            )
        elif stripped.startswith("inet6 "):
            parts = stripped.split()
            cidr = parts[1]
            address, _, prefix = cidr.partition("/")
            current["addresses"].append(
                {
                    "family": "ipv6",
                    "address": address,
                    "netmask": prefix or None,
                    "is_loopback": address == "::1",
                }
            )

    if current:
        interfaces.append(current)

    return interfaces


def parse_ifconfig(output: str) -> list[dict[str, object]]:
    """Parse `ifconfig` output from Unix-like systems."""

    interfaces: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in output.splitlines():
        if raw_line and not raw_line.startswith(("\t", " ")):
            if current:
                interfaces.append(current)
            name, _, remainder = raw_line.partition(":")
            flags_match = re.search(r"flags=\d+<([^>]*)>", remainder)
            mtu_match = re.search(r"\bmtu\s+(\d+)", remainder)
            flags = {
                flag.strip()
                for flag in (flags_match.group(1).split(",") if flags_match else [])
                if flag.strip()
            }
            current = {
                "name": name.strip(),
                "is_up": "UP" in flags,
                "mtu": int(mtu_match.group(1)) if mtu_match else None,
                "mac_address": None,
                "addresses": [],
            }
            continue

        if current is None:
            continue

        stripped = raw_line.strip()
        if stripped.startswith("ether "):
            parts = stripped.split()
            if len(parts) >= 2:
                current["mac_address"] = parts[1]
        elif stripped.startswith("inet "):
            parts = stripped.split()
            address = parts[1]
            netmask = None
            if "netmask" in parts:
                netmask = parts[parts.index("netmask") + 1]
            current["addresses"].append(
                {
                    "family": "ipv4",
                    "address": address,
                    "netmask": netmask,
                    "is_loopback": address.startswith("127."),
                }
            )
        elif stripped.startswith("inet6 "):
            parts = stripped.split()
            address = parts[1]
            current["addresses"].append(
                {
                    "family": "ipv6",
                    "address": address,
                    "netmask": None,
                    "is_loopback": address == "::1",
                }
            )

    if current:
        interfaces.append(current)

    return interfaces


def parse_ipconfig(output: str) -> list[dict[str, object]]:
    """Parse Windows `ipconfig /all` output into interface records."""

    interfaces: list[dict[str, object]] = []
    current: dict[str, object] | None = None

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if re.match(r"^[^\s].*:$", line):
            if current:
                interfaces.append(current)
            name = _extract_windows_interface_name(line.rstrip(":"))
            current = {
                "name": name,
                "is_up": False,
                "mtu": None,
                "mac_address": None,
                "addresses": [],
            }
            continue

        if current is None:
            continue

        stripped = line.strip()
        if ":" not in stripped:
            continue
        field, _, value = stripped.partition(":")
        normalized_field = _normalize_windows_label(field)
        value = value.strip()

        if normalized_field == "physicaladdress":
            current["mac_address"] = value.strip() or None
        elif normalized_field in {"ipv4address", "autoconfigurationipv4address"}:
            address = _strip_windows_address_annotations(value)
            current["addresses"].append(
                {
                    "family": "ipv4",
                    "address": address,
                    "netmask": None,
                    "is_loopback": address.startswith("127."),
                }
            )
            current["is_up"] = True
        elif normalized_field in {"ipv6address", "temporaryipv6address", "linklocalipv6address"}:
            address = _strip_windows_address_annotations(value)
            current["addresses"].append(
                {
                    "family": "ipv6",
                    "address": address,
                    "netmask": None,
                    "is_loopback": address == "::1",
                }
            )
            current["is_up"] = True
        elif normalized_field == "mediastate":
            current["is_up"] = "disconnected" not in stripped.lower()

    if current:
        interfaces.append(current)

    return interfaces


def parse_ping_output(output: str) -> dict[str, float | None]:
    """Extract latency and packet loss from ping output."""

    latency_match = re.search(r"=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+\s*ms", output)
    if latency_match:
        return {
            "average_latency_ms": float(latency_match.group(1)),
            "packet_loss_percent": _extract_packet_loss(output),
        }

    windows_latency_match = re.search(r"Average = (\d+)ms", output)
    if windows_latency_match:
        return {
            "average_latency_ms": float(windows_latency_match.group(1)),
            "packet_loss_percent": _extract_packet_loss(output),
        }

    return {"average_latency_ms": None, "packet_loss_percent": _extract_packet_loss(output)}


def parse_traceroute_output(output: str) -> list[dict[str, object]]:
    """Parse a traceroute or tracert output into hops."""

    hops: list[dict[str, object]] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or not re.match(r"^\d+", line):
            continue

        hop_match = re.match(r"^(\d+)\s+(.*)$", line)
        if not hop_match:
            continue
        hop_number = int(hop_match.group(1))
        remainder = hop_match.group(2).strip()
        latency_values = [
            float(value)
            for value in re.findall(r"<?(\d+(?:\.\d+)?)\s*ms", remainder, re.IGNORECASE)
        ]
        bracket_match = re.search(r"\[([^\]]+)\]", remainder)
        address_match = bracket_match or re.search(
            r"\b((?:\d{1,3}\.){3}\d{1,3}|(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f:]+)\b",
            remainder,
        )
        address = (
            bracket_match.group(1)
            if bracket_match
            else (address_match.group(1) if address_match else None)
        )
        host = _extract_trace_host(remainder, address)
        note = None
        if "*" in remainder and not latency_values and address is None:
            note = "timeout"
        unreachable_match = re.search(
            r"(![A-Z]+|request timed out\.|destination .*? unreachable\.?|general failure\.)",
            remainder,
            re.IGNORECASE,
        )
        if unreachable_match:
            note = unreachable_match.group(1).lower()
        hops.append(
            {
                "hop": hop_number,
                "host": host,
                "address": address,
                "latency_ms": round(sum(latency_values) / len(latency_values), 1) if latency_values else None,
                "note": note,
            }
        )

    return hops


def parse_ip_neigh(output: str) -> list[dict[str, object]]:
    """Parse Linux `ip neigh show` output into neighbor entries."""

    neighbors: list[dict[str, object]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        ip_match = re.match(r"^(\S+)\s+dev\s+(\S+)(?:\s+lladdr\s+(\S+))?(?:\s+router)?\s+(\S+)?", line)
        if not ip_match:
            continue

        mac_address = _normalize_mac_address(ip_match.group(3))
        state = ip_match.group(4)
        neighbors.append(
            {
                "ip_address": ip_match.group(1),
                "mac_address": mac_address,
                "interface": ip_match.group(2),
                "state": state,
            }
        )
    return neighbors


def parse_arp_table(output: str) -> list[dict[str, object]]:
    """Parse `arp -a` output from macOS, Linux, or Windows."""

    neighbors: list[dict[str, object]] = []
    current_interface: str | None = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        interface_header_match = re.match(r"^Interface:\s+(\S+)", line, re.IGNORECASE)
        if interface_header_match:
            current_interface = interface_header_match.group(1)
            continue

        named_entry_match = re.search(
            r"\(([^)]+)\)\s+at\s+(\S+)(?:\s+on\s+(\S+))?",
            line,
            re.IGNORECASE,
        )
        if named_entry_match:
            raw_mac = named_entry_match.group(2)
            neighbors.append(
                {
                    "ip_address": named_entry_match.group(1),
                    "mac_address": _normalize_mac_address(raw_mac),
                    "interface": named_entry_match.group(3),
                    "state": "incomplete" if raw_mac.lower() == "<incomplete>" else None,
                }
            )
            continue

        windows_entry_match = re.match(
            r"^((?:\d{1,3}\.){3}\d{1,3})\s+(\S+)\s+(\S+)$",
            line,
        )
        if windows_entry_match:
            neighbors.append(
                {
                    "ip_address": windows_entry_match.group(1),
                    "mac_address": _normalize_mac_address(windows_entry_match.group(2)),
                    "interface": current_interface,
                    "state": windows_entry_match.group(3).lower(),
                }
            )

    return neighbors


def parse_resolv_conf(output: str) -> list[str]:
    """Parse `/etc/resolv.conf`-style output into a resolver list."""

    resolvers: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("nameserver"):
            parts = line.split()
            if len(parts) >= 2:
                resolvers.append(parts[1])
    return resolvers


def _extract_metric(line: str) -> int | None:
    metric_match = re.search(r"\bmetric\s+(\d+)", line)
    return int(metric_match.group(1)) if metric_match else None


def _extract_packet_loss(output: str) -> float | None:
    unix_match = re.search(r"(\d+(?:\.\d+)?)%\s*packet loss", output)
    if unix_match:
        return float(unix_match.group(1))
    windows_match = re.search(r"\((\d+)% loss\)", output)
    if windows_match:
        return float(windows_match.group(1))
    return None


def _normalize_mac_address(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"<incomplete>", "incomplete"}:
        return None
    return lowered.replace("-", ":")


def _extract_linux_route_qualifier(line: str) -> tuple[str | None, str]:
    for qualifier in ("unreachable", "blackhole", "prohibit", "throw"):
        if line.startswith(f"{qualifier} "):
            return f"Default route is marked {qualifier}." if " default" in f" {line}" else qualifier, line[len(qualifier) + 1 :]
    return None, line


def _select_default_route(routes: list[dict[str, object]]) -> dict[str, object] | None:
    if not routes:
        return None
    return min(
        routes,
        key=lambda route: (
            1 if route.get("note") else 0,
            route.get("metric") if isinstance(route.get("metric"), int) else 1_000_000,
        ),
    )


def _default_route_state(has_default_route: bool, observations: list[str]) -> str:
    if not has_default_route:
        return "missing"
    return "suspect" if observations else "present"


def _default_route_note(gateway: str | None, interface: str | None) -> str | None:
    if not gateway and not interface:
        return "Default route entry was incomplete."
    if gateway and gateway.lower() == "on-link":
        return "Default route exists but is on-link without an explicit gateway."
    if gateway and gateway.lower().startswith("link#"):
        return f"Default route uses link-scoped gateway {gateway}, so next-hop reachability is less explicit."
    return None


def _dedupe_messages(messages: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for message in messages:
        if not message or message in seen:
            continue
        seen.add(message)
        ordered.append(message)
    return ordered


def _extract_windows_interface_name(header: str) -> str:
    lowered = header.lower()
    if "adapter" in lowered:
        return header.split("adapter", 1)[1].strip()
    return header.strip()


def _normalize_windows_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _strip_windows_address_annotations(value: str) -> str:
    return re.sub(r"\([^)]*\)", "", value).strip()


def _extract_trace_host(remainder: str, address: str | None) -> str | None:
    if not remainder:
        return address
    body = re.sub(r"<?\d+(?:\.\d+)?\s*ms", " ", remainder, flags=re.IGNORECASE)
    body = body.replace("*", " ")
    if address and f"[{address}]" in remainder:
        body = body.replace(f"[{address}]", " ")
    elif address:
        body = body.replace(address, " ")
    candidate = " ".join(body.split()).strip()
    if not candidate:
        return address
    lowered = candidate.lower()
    if lowered.startswith(("request timed out", "destination ", "trace complete", "general failure")):
        return None
    return candidate.split()[0]
