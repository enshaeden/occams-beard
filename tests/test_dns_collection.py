"""Tests for DNS collection behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.collectors.dns import collect_dns_state
from occams_beard.utils.resolution import HostnameResolutionResult


class DnsCollectionTests(unittest.TestCase):
    """Validate bounded DNS hostname resolution behavior."""

    @patch("occams_beard.collectors.dns._read_resolvers", return_value=["1.1.1.1"])
    @patch("occams_beard.collectors.dns.resolve_hostname_addresses")
    def test_collect_dns_state_surfaces_hostname_resolution_timeout(
        self,
        mock_resolve,
        _mock_resolvers,
    ) -> None:
        mock_resolve.return_value = HostnameResolutionResult(
            addresses=[],
            error="hostname-resolution-timeout",
            timed_out=True,
            duration_ms=2000,
        )

        state, warnings = collect_dns_state(["github.com"])

        self.assertEqual(state.checks[0].hostname, "github.com")
        self.assertFalse(state.checks[0].success)
        self.assertEqual(state.checks[0].error, "hostname-resolution-timeout")
        self.assertEqual(state.checks[0].duration_ms, 2000)
        self.assertEqual([warning.code for warning in warnings], ["hostname-resolution-timeout"])

    @patch("occams_beard.collectors.dns._read_resolvers", return_value=["1.1.1.1"])
    @patch("occams_beard.collectors.dns.resolve_hostname_addresses")
    def test_collect_dns_state_reports_incremental_progress(
        self,
        mock_resolve,
        _mock_resolvers,
    ) -> None:
        mock_resolve.side_effect = [
            HostnameResolutionResult(
                addresses=["140.82.121.3"],
                error=None,
                timed_out=False,
                duration_ms=12,
            ),
            HostnameResolutionResult(
                addresses=[],
                error="no-addresses-returned",
                timed_out=False,
                duration_ms=9,
            ),
        ]
        progress_updates: list[int] = []

        state, warnings = collect_dns_state(
            ["github.com", "pypi.org"],
            progress_callback=progress_updates.append,
        )

        self.assertEqual(progress_updates, [1, 2, 3])
        self.assertEqual([check.hostname for check in state.checks], ["github.com", "pypi.org"])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
