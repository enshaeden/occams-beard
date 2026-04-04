"""Tests for registered diagnostic domains and execution planning."""

from __future__ import annotations

import unittest

from occams_beard.domain_registry import build_execution_plan, iter_registered_domains
from occams_beard.runner import DiagnosticsRunOptions


class DomainRegistryTests(unittest.TestCase):
    """Protect the explicit registry and execution-plan contract."""

    def test_build_execution_plan_always_includes_host_and_selected_domains(self) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["dns", "services", "vpn"],
            targets=[],
            dns_hosts=["github.com"],
        )

        plan = build_execution_plan(options)

        self.assertEqual(
            [planned.domain for planned in plan],
            ["host", "dns", "services", "vpn"],
        )

    def test_registered_domains_expose_unique_domain_ids(self) -> None:
        registered = iter_registered_domains()

        self.assertEqual(
            [definition.domain for definition in registered],
            list(dict.fromkeys(definition.domain for definition in registered)),
        )


if __name__ == "__main__":
    unittest.main()
