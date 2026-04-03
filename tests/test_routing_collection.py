"""Tests for routing collection normalization and warnings."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.collectors.routing import collect_route_summary
from occams_beard.utils.subprocess import CommandResult


class RoutingCollectionTests(unittest.TestCase):
    """Validate route summary normalization and degraded-data warnings."""

    @patch("occams_beard.collectors.routing.current_platform", return_value="windows")
    @patch("occams_beard.collectors.routing.windows.read_routes")
    def test_collect_route_summary_preserves_route_observations(
        self,
        mock_read_routes,
        _mock_platform,
    ) -> None:
        mock_read_routes.return_value = (
            {
                "default_gateway": "10.10.10.1",
                "default_interface": "10.10.10.50",
                "has_default_route": True,
                "routes": [
                    {
                        "destination": "default",
                        "gateway": "10.10.10.1",
                        "interface": "10.10.10.50",
                        "metric": 25,
                        "note": None,
                    }
                ],
                "default_route_state": "suspect",
                "observations": ["Multiple Windows default routes were collected."],
                "parse_warnings": [],
            },
            CommandResult(
                args=("route", "print"),
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=5,
            ),
        )

        route_summary, warnings = collect_route_summary()

        self.assertEqual(route_summary.default_route_state, "suspect")
        self.assertEqual(route_summary.observations, ["Multiple Windows default routes were collected."])
        self.assertEqual(warnings, [])

    @patch("occams_beard.collectors.routing.current_platform", return_value="linux")
    @patch("occams_beard.collectors.routing.linux.read_routes")
    def test_collect_route_summary_surfaces_parse_warnings(
        self,
        mock_read_routes,
        _mock_platform,
    ) -> None:
        mock_read_routes.return_value = (
            {
                "default_gateway": None,
                "default_interface": None,
                "has_default_route": False,
                "routes": [],
                "default_route_state": "missing",
                "observations": [],
                "parse_warnings": ["Ignored a malformed Linux route line with no tokens."],
            },
            CommandResult(
                args=("ip", "route", "show"),
                returncode=0,
                stdout="",
                stderr="",
                duration_ms=5,
            ),
        )

        _route_summary, warnings = collect_route_summary()

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].code, "route-data-warning")
        self.assertIn("malformed Linux route line", warnings[0].message)


if __name__ == "__main__":
    unittest.main()
