"""Tests for configured service collection."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.collectors.services import collect_service_state
from occams_beard.models import TcpConnectivityCheck, TcpTarget


class ServiceCollectionTests(unittest.TestCase):
    """Validate per-target service progress reporting."""

    @patch("occams_beard.collectors.services.check_tcp_target")
    def test_collect_service_state_reports_incremental_progress(
        self,
        mock_check_tcp_target,
    ) -> None:
        mock_check_tcp_target.side_effect = [
            TcpConnectivityCheck(
                target=TcpTarget(host="github.com", port=443),
                success=True,
                latency_ms=24.5,
                duration_ms=24,
            ),
            TcpConnectivityCheck(
                target=TcpTarget(host="1.1.1.1", port=53),
                success=False,
                error="connection-refused",
                duration_ms=42,
            ),
        ]
        progress_updates: list[int] = []

        state = collect_service_state(
            [
                TcpTarget(host="github.com", port=443),
                TcpTarget(host="1.1.1.1", port=53),
            ],
            progress_callback=progress_updates.append,
        )

        self.assertEqual(progress_updates, [1, 2])
        self.assertEqual(len(state.checks), 2)
        self.assertTrue(state.checks[0].success)
        self.assertFalse(state.checks[1].success)


if __name__ == "__main__":
    unittest.main()
