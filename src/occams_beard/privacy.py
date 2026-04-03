"""Redaction helpers for support-bundle exports."""

from __future__ import annotations

import copy
import ipaddress
import re
from collections import Counter, defaultdict
from typing import Any

from occams_beard.models import (
    EndpointDiagnosticResult,
    RawCommandCapture,
    RedactionLevel,
    RedactionSummary,
)

_MAC_ADDRESS_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
_IP_ADDRESS_TOKEN_RE = re.compile(
    r"(?<![0-9A-Fa-f:.])(?=[0-9A-Fa-f:.]*[.:])[0-9A-Fa-f:.]+(?![0-9A-Fa-f:.])"
)


class BundleRedactor:
    """Consistent redaction engine for structured results and raw text artifacts."""

    def __init__(self, result: EndpointDiagnosticResult, level: RedactionLevel) -> None:
        self.level = level
        self._counts: Counter[str] = Counter()
        self._notes: list[str] = []
        self._exact_replacements: dict[str, tuple[str, str]] = {}
        self._token_counters: defaultdict[str, int] = defaultdict(int)
        self._register_sensitive_values(result)
        self._notes.append(
            {
                "none": "No redaction was applied.",
                "safe": (
                    "Safe redaction hides endpoint identifiers, hostnames, "
                    "private addresses, and MAC addresses while preserving "
                    "overall diagnostic shape."
                ),
                "strict": (
                    "Strict redaction additionally hides public IPs, interface "
                    "names, and target labels."
                ),
            }[level]
        )

    def redact_data(self, payload: Any) -> Any:
        """Return a redacted copy of a JSON-like payload."""

        return self._redact_value(copy.deepcopy(payload))

    def redact_text(self, text: str) -> str:
        """Return a redacted copy of free-form text."""

        redacted = text
        if self.level == "none":
            return redacted

        for original, (replacement, category) in sorted(
            self._exact_replacements.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            occurrences = redacted.count(original)
            if occurrences:
                redacted = redacted.replace(original, replacement)
                self._counts[category] += occurrences

        redacted = self._replace_ip_matches(redacted)
        redacted = self._replace_mac_matches(redacted)
        return redacted

    def redact_raw_commands(self, captures: list[RawCommandCapture]) -> list[dict[str, Any]]:
        """Return redacted raw-command capture payloads."""

        redacted_items: list[dict[str, Any]] = []
        for capture in captures:
            redacted_items.append(
                {
                    "command": [self.redact_text(part) for part in capture.command],
                    "returncode": capture.returncode,
                    "stdout": self.redact_text(capture.stdout),
                    "stderr": self.redact_text(capture.stderr),
                    "duration_ms": capture.duration_ms,
                    "timed_out": capture.timed_out,
                    "error": self.redact_text(capture.error) if capture.error else None,
                }
            )
        return redacted_items

    def summary(self) -> RedactionSummary:
        """Return the accumulated redaction summary."""

        return RedactionSummary(
            level=self.level,
            counts=dict(sorted(self._counts.items())),
            notes=self._notes,
        )

    def registered_values(self) -> tuple[str, ...]:
        """Return the exact sensitive values registered for this result."""

        return tuple(self._exact_replacements)

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: self._redact_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._redact_value(item) for item in value]
        if isinstance(value, str):
            return self.redact_text(value)
        return value

    def _register_sensitive_values(self, result: EndpointDiagnosticResult) -> None:
        self._register("endpoint-host", result.facts.host.hostname)
        self._register("user", result.facts.host.current_user)

        for local_address in result.facts.network.local_addresses:
            self._register_address(local_address)
        for interface in result.facts.network.interfaces:
            if self.level == "strict":
                self._register("interface", interface.name)
            self._register("mac-address", interface.mac_address)
            for interface_address in interface.addresses:
                self._register_address(interface_address.address)
        for neighbor in result.facts.network.arp_neighbors:
            self._register_address(neighbor.ip_address)
            self._register("mac-address", neighbor.mac_address)
            if self.level == "strict":
                self._register("interface", neighbor.interface)

        self._register_address(result.facts.network.route_summary.default_gateway)
        if self.level == "strict":
            self._register("interface", result.facts.network.route_summary.default_interface)
        for resolver in result.facts.dns.resolvers:
            self._register_address_or_host(resolver)
        for dns_check in result.facts.dns.checks:
            self._register("hostname", dns_check.hostname)
            for resolved in dns_check.resolved_addresses:
                self._register_address(resolved)
        for tcp_check in result.facts.connectivity.tcp_checks:
            self._register_target_host(tcp_check.target.host)
            self._register_address(tcp_check.ip_used)
            if self.level == "strict":
                self._register("label", tcp_check.target.label)
        for ping in result.facts.connectivity.ping_checks:
            self._register_target_host(ping.target)
        for trace in result.facts.connectivity.trace_results:
            self._register_target_host(trace.target)
            self._register_address_or_host(trace.target_address)
            for hop in trace.hops:
                self._register_address_or_host(hop.address)
                self._register("hostname", hop.host)
        for service_check in result.facts.services.checks:
            self._register_target_host(service_check.target.host)
            if self.level == "strict":
                self._register("label", service_check.target.label)
        for signal in result.facts.vpn.signals:
            if self.level == "strict":
                self._register("interface", signal.interface_name)

    def _register_target_host(self, value: str | None) -> None:
        if not value:
            return
        try:
            ipaddress.ip_address(value)
        except ValueError:
            self._register("hostname", value)
            return
        self._register_address(value)

    def _register_address_or_host(self, value: str | None) -> None:
        if not value:
            return
        try:
            ipaddress.ip_address(value)
        except ValueError:
            self._register("hostname", value)
            return
        self._register_address(value)

    def _register_address(self, value: str | None) -> None:
        if not value or self.level == "none":
            return
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError:
            return

        if self.level == "safe":
            if parsed.is_private or parsed.is_loopback or parsed.is_link_local:
                self._register("private-ip", value)
        else:
            category = (
                "private-ip"
                if parsed.is_private or parsed.is_loopback or parsed.is_link_local
                else "ip"
            )
            self._register(category, value)

    def _register(self, category: str, value: str | None) -> None:
        if not value or self.level == "none":
            return
        if value in self._exact_replacements:
            return
        self._token_counters[category] += 1
        token = f"<{category}-{self._token_counters[category]}>"
        self._exact_replacements[value] = (token, category)

    def _replace_ip_matches(self, text: str) -> str:
        def _replacement(match: re.Match[str]) -> str:
            value = match.group(0)
            try:
                parsed = ipaddress.ip_address(value)
            except ValueError:
                return value

            if self.level == "safe" and not (
                parsed.is_private or parsed.is_loopback or parsed.is_link_local
            ):
                return value
            category = (
                "private-ip"
                if parsed.is_private or parsed.is_loopback or parsed.is_link_local
                else "ip"
            )
            replacement = self._exact_replacements.get(value)
            if replacement is None:
                self._register(category, value)
                replacement = self._exact_replacements[value]
            self._counts[category] += 1
            return replacement[0]

        return _IP_ADDRESS_TOKEN_RE.sub(_replacement, text)

    def _replace_mac_matches(self, text: str) -> str:
        def _replacement(match: re.Match[str]) -> str:
            value = match.group(0)
            replacement = self._exact_replacements.get(value)
            if replacement is None:
                self._register("mac-address", value)
                replacement = self._exact_replacements[value]
            self._counts["mac-address"] += 1
            return replacement[0]

        return _MAC_ADDRESS_RE.sub(_replacement, text)
