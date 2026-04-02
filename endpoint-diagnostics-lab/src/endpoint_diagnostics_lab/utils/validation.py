"""Validation helpers for CLI inputs and normalized data."""

from __future__ import annotations

import json
import ipaddress
from pathlib import Path
from typing import Iterable

from endpoint_diagnostics_lab.models import TcpTarget


def parse_host_port_target(raw_value: str) -> TcpTarget:
    """Parse a CLI host:port string into a target model."""

    if ":" not in raw_value:
        raise ValueError(f"Target must use host:port format: {raw_value}")

    host, port_text = raw_value.rsplit(":", 1)
    host = host.strip()
    if not host:
        raise ValueError(f"Target host is empty: {raw_value}")

    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError(f"Target port is not an integer: {raw_value}") from exc

    if not 1 <= port <= 65535:
        raise ValueError(f"Target port must be between 1 and 65535: {raw_value}")

    return TcpTarget(host=host, port=port, label=None)


def load_targets_file(path_text: str) -> list[TcpTarget]:
    """Load TCP targets from a JSON file."""

    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Target file does not exist: {path}") from exc
    except OSError as exc:
        raise ValueError(f"Target file could not be read: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Target file is not valid JSON: {path}") from exc

    if not isinstance(payload, list):
        raise ValueError(f"Target file must contain a JSON array: {path}")

    targets: list[TcpTarget] = []
    for index, item in enumerate(payload):
        if isinstance(item, str):
            targets.append(parse_host_port_target(item))
            continue
        if not isinstance(item, dict):
            raise ValueError(
                f"Target file entry {index} must be a string or object with host and port."
            )

        host = item.get("host")
        port = item.get("port")
        label = item.get("label")
        if not isinstance(host, str) or not host.strip():
            raise ValueError(f"Target file entry {index} has an invalid host value.")
        if not isinstance(port, int):
            raise ValueError(f"Target file entry {index} has an invalid port value.")

        target = parse_host_port_target(f"{host}:{port}")
        if label is not None:
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"Target file entry {index} has an invalid label value.")
            target.label = label.strip()
        targets.append(target)

    return targets


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    """Return unique values while preserving their first-seen order."""

    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def is_private_or_loopback_host(host: str) -> bool:
    """Return True when the host string is an RFC1918 or loopback address."""

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_private or address.is_loopback
