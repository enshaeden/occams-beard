"""Parsing helpers for common system command outputs."""

from __future__ import annotations

import re


def parse_linux_ip_route(output: str) -> dict[str, object]:
    """Parse `ip route show` output into a compact structure."""

    default_gateway: str | None = None
    default_interface: str | None = None
    routes: list[dict[str, object]] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("default "):
            gateway_match = re.search(r"\bvia\s+(\S+)", line)
            interface_match = re.search(r"\bdev\s+(\S+)", line)
            default_gateway = gateway_match.group(1) if gateway_match else None
            default_interface = interface_match.group(1) if interface_match else None
            routes.append(
                {
                    "destination": "default",
                    "gateway": default_gateway,
                    "interface": default_interface,
                    "metric": _extract_metric(line),
                }
            )
            continue

        tokens = line.split()
        destination = tokens[0]
        gateway_match = re.search(r"\bvia\s+(\S+)", line)
        interface_match = re.search(r"\bdev\s+(\S+)", line)
        routes.append(
            {
                "destination": destination,
                "gateway": gateway_match.group(1) if gateway_match else None,
                "interface": interface_match.group(1) if interface_match else None,
                "metric": _extract_metric(line),
            }
        )

    return {
        "default_gateway": default_gateway,
        "default_interface": default_interface,
        "has_default_route": default_gateway is not None or default_interface is not None,
        "routes": routes,
    }


def parse_route_get_default(output: str) -> dict[str, object]:
    """Parse macOS `route -n get default` output."""

    gateway_match = re.search(r"^\s*gateway:\s+(\S+)", output, re.MULTILINE)
    interface_match = re.search(r"^\s*interface:\s+(\S+)", output, re.MULTILINE)
    gateway = gateway_match.group(1) if gateway_match else None
    interface = interface_match.group(1) if interface_match else None

    routes = []
    if gateway or interface:
        routes.append(
            {
                "destination": "default",
                "gateway": gateway,
                "interface": interface,
                "metric": None,
            }
        )

    return {
        "default_gateway": gateway,
        "default_interface": interface,
        "has_default_route": gateway is not None or interface is not None,
        "routes": routes,
    }


def parse_route_print(output: str) -> dict[str, object]:
    """Parse Windows `route print` output into a compact structure."""

    default_gateway: str | None = None
    default_interface: str | None = None
    routes: list[dict[str, object]] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not re.match(r"^\d+\.\d+\.\d+\.\d+", line):
            continue

        parts = line.split()
        if len(parts) < 5:
            continue
        destination, netmask, gateway, interface, metric_text = parts[:5]
        destination_label = "default" if destination == "0.0.0.0" and netmask == "0.0.0.0" else destination
        metric = int(metric_text) if metric_text.isdigit() else None
        routes.append(
            {
                "destination": destination_label,
                "gateway": gateway,
                "interface": interface,
                "metric": metric,
            }
        )
        if destination_label == "default":
            default_gateway = gateway
            default_interface = interface

    return {
        "default_gateway": default_gateway,
        "default_interface": default_interface,
        "has_default_route": default_gateway is not None,
        "routes": routes,
    }


def parse_netstat_rn(output: str) -> dict[str, object]:
    """Parse Unix `netstat -rn` output."""

    default_gateway: str | None = None
    default_interface: str | None = None
    routes: list[dict[str, object]] = []

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("Routing", "Destination", "Internet:", "Kernel")):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        destination = parts[0]
        gateway = parts[1]
        interface = parts[-1]
        metric = None
        if destination in {"default", "0.0.0.0"}:
            default_gateway = gateway
            default_interface = interface
            destination = "default"
        routes.append(
            {
                "destination": destination,
                "gateway": gateway,
                "interface": interface,
                "metric": metric,
            }
        )

    return {
        "default_gateway": default_gateway,
        "default_interface": default_interface,
        "has_default_route": default_gateway is not None or default_interface is not None,
        "routes": routes,
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
                "name": match.group(1),
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
        if line.endswith(":") and "adapter" in line.lower():
            if current:
                interfaces.append(current)
            name = line.rstrip(":").split("adapter", 1)[1].strip()
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
        if "Physical Address" in stripped:
            _, _, value = stripped.partition(":")
            current["mac_address"] = value.strip() or None
        elif "IPv4 Address" in stripped:
            _, _, value = stripped.partition(":")
            address = value.replace("(Preferred)", "").strip()
            current["addresses"].append(
                {
                    "family": "ipv4",
                    "address": address,
                    "netmask": None,
                    "is_loopback": address.startswith("127."),
                }
            )
            current["is_up"] = True
        elif "IPv6 Address" in stripped or "Link-local IPv6 Address" in stripped:
            _, _, value = stripped.partition(":")
            address = value.replace("(Preferred)", "").strip()
            current["addresses"].append(
                {
                    "family": "ipv6",
                    "address": address,
                    "netmask": None,
                    "is_loopback": address == "::1",
                }
            )
            current["is_up"] = True
        elif "Media State" in stripped:
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

        tokens = line.split()
        hop_number = int(tokens[0])
        latency_match = re.search(r"(\d+(?:\.\d+)?)\s*ms", line, re.IGNORECASE)
        address_match = re.search(
            r"\b((?:\d{1,3}\.){3}\d{1,3}|(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f:]+)\b",
            line,
        )
        host = address_match.group(1) if address_match else None
        note = None
        if "*" in line:
            note = "timeout"
        unreachable_match = re.search(
            r"(![A-Z]+|request timed out\.|destination .*? unreachable)",
            line,
            re.IGNORECASE,
        )
        if unreachable_match:
            note = unreachable_match.group(1)
        hops.append(
            {
                "hop": hop_number,
                "host": host,
                "address": address_match.group(1) if address_match else None,
                "latency_ms": float(latency_match.group(1)) if latency_match else None,
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
