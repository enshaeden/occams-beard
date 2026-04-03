"""Tests for the shared diagnostics runner."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.defaults import DEFAULT_CHECKS
from occams_beard.models import DnsState, Finding, HostBasics, TcpTarget
from occams_beard.runner import DiagnosticsRunOptions, build_run_options, run_diagnostics


class RunnerTests(unittest.TestCase):
    """Validate shared runner option resolution and execution flow."""

    def test_build_run_options_uses_defaults(self) -> None:
        options = build_run_options()

        self.assertEqual(options.selected_checks, DEFAULT_CHECKS)
        self.assertEqual([target.host for target in options.targets], ["github.com", "1.1.1.1"])
        self.assertEqual(options.dns_hosts, ["github.com", "python.org"])
        self.assertFalse(options.enable_ping)
        self.assertFalse(options.enable_trace)

    def test_run_diagnostics_returns_result_and_skips_unselected_collectors(self) -> None:
        options = DiagnosticsRunOptions(
            selected_checks=["dns"],
            targets=[TcpTarget(host="github.com", port=443)],
            dns_hosts=["github.com"],
        )
        finding = Finding(
            identifier="dns-degraded",
            severity="medium",
            title="DNS is degraded",
            summary="A hostname failed to resolve.",
            evidence=["github.com failed to resolve."],
            probable_cause="DNS resolution is partially failing.",
            fault_domain="dns",
            confidence=0.88,
        )

        with patch(
            "occams_beard.runner.collect_host_basics",
            return_value=(
                HostBasics(
                    hostname="demo-host",
                    operating_system="Linux",
                    kernel="6.8.0",
                    current_user="operator",
                    uptime_seconds=120,
                ),
                [],
            ),
        ), patch(
            "occams_beard.runner.collect_dns_state",
            return_value=(DnsState(), []),
        ), patch(
            "occams_beard.runner.evaluate_selected_findings",
            return_value=([finding], "dns"),
        ), patch("occams_beard.runner.collect_resource_state") as mock_resources, patch(
            "occams_beard.runner.collect_storage_state"
        ) as mock_storage, patch("occams_beard.runner.collect_network_state") as mock_network, patch(
            "occams_beard.runner.collect_route_summary"
        ) as mock_routes, patch(
            "occams_beard.runner.collect_connectivity_state"
        ) as mock_connectivity, patch(
            "occams_beard.runner.collect_service_state"
        ) as mock_services, patch("occams_beard.runner.collect_vpn_state") as mock_vpn:
            result = run_diagnostics(options)

        self.assertEqual(result.metadata.selected_checks, ["dns"])
        self.assertEqual(result.probable_fault_domain, "dns")
        self.assertEqual(result.findings[0].identifier, "dns-degraded")
        self.assertEqual(result.facts.host.hostname, "demo-host")
        mock_resources.assert_not_called()
        mock_storage.assert_not_called()
        mock_network.assert_not_called()
        mock_routes.assert_not_called()
        mock_connectivity.assert_not_called()
        mock_services.assert_not_called()
        mock_vpn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
