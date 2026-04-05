"""Shared defaults for operator-facing diagnostics execution."""

from __future__ import annotations

from occams_beard.models import TcpTarget

DEFAULT_CHECKS = [
    "host",
    "time",
    "resources",
    "storage",
    "network",
    "routing",
    "dns",
    "connectivity",
    "vpn",
    "services",
]

DEFAULT_DNS_HOSTS = ["github.com", "python.org"]

DEFAULT_TIME_REFERENCE_LABEL = "GitHub HTTPS response date"
DEFAULT_TIME_REFERENCE_URL = "https://github.com/"

DEFAULT_TCP_TARGETS = (
    TcpTarget(host="github.com", port=443, label="github-https"),
    TcpTarget(host="1.1.1.1", port=53, label="cloudflare-dns"),
)

ALLOWED_CHECKS = tuple(DEFAULT_CHECKS)
