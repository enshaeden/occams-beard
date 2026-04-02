"""Tests for CLI validation helpers."""

from __future__ import annotations

import tempfile
import unittest

from endpoint_diagnostics_lab.utils.validation import load_targets_file, parse_host_port_target


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


if __name__ == "__main__":
    unittest.main()
