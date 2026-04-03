"""Tests for CLI validation helpers."""

from __future__ import annotations

import tempfile
import unittest

from occams_beard.defaults import DEFAULT_CHECKS, DEFAULT_TCP_TARGETS
from occams_beard.utils.validation import (
    load_targets_file,
    parse_check_selection,
    parse_host_port_target,
    resolve_dns_hosts,
    resolve_tcp_targets,
)


class ValidationTests(unittest.TestCase):
    """Validate target parsing helpers."""

    def test_parse_host_port_target_rejects_invalid_port(self) -> None:
        with self.assertRaises(ValueError):
            parse_host_port_target("github.com:99999")

    def test_load_targets_file_supports_strings_and_objects(self) -> None:
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8") as temp_file:
            temp_file.write(
                """
[
  "github.com:443",
  {"host": "1.1.1.1", "port": 53, "label": "cloudflare-dns"}
]
""".strip()
            )
            temp_file.flush()

            targets = load_targets_file(temp_file.name)

        self.assertEqual(len(targets), 2)
        self.assertEqual(targets[0].host, "github.com")
        self.assertEqual(targets[1].port, 53)
        self.assertEqual(targets[1].label, "cloudflare-dns")

    def test_load_targets_file_rejects_invalid_payload_shape(self) -> None:
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8") as temp_file:
            temp_file.write('{"host": "github.com", "port": 443}')
            temp_file.flush()

            with self.assertRaises(ValueError):
                load_targets_file(temp_file.name)

    def test_parse_check_selection_rejects_unsupported_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "Supported values:"):
            parse_check_selection(
                "dns,invalid",
                allowed_checks=DEFAULT_CHECKS,
                default_checks=DEFAULT_CHECKS,
            )

    def test_resolve_dns_hosts_uses_defaults_and_deduplicates(self) -> None:
        self.assertEqual(
            resolve_dns_hosts([], default_hosts=["github.com", "python.org"]),
            ["github.com", "python.org"],
        )
        self.assertEqual(
            resolve_dns_hosts(["github.com", "github.com", "python.org"], default_hosts=[]),
            ["github.com", "python.org"],
        )

    def test_resolve_tcp_targets_uses_defaults_when_none_are_supplied(self) -> None:
        targets = resolve_tcp_targets([], None, default_targets=DEFAULT_TCP_TARGETS)

        self.assertEqual([target.host for target in targets], ["github.com", "1.1.1.1"])
        self.assertIsNot(targets[0], DEFAULT_TCP_TARGETS[0])

    def test_resolve_tcp_targets_combines_cli_and_file_targets(self) -> None:
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8") as temp_file:
            temp_file.write('[{"host": "1.1.1.1", "port": 53, "label": "cloudflare-dns"}]')
            temp_file.flush()

            targets = resolve_tcp_targets(
                ["github.com:443", "status.example.com:8443"],
                temp_file.name,
                default_targets=DEFAULT_TCP_TARGETS,
            )

        self.assertEqual(
            [(target.host, target.port, target.label) for target in targets],
            [
                ("github.com", 443, None),
                ("status.example.com", 8443, None),
                ("1.1.1.1", 53, "cloudflare-dns"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
