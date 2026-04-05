"""Tests for local clock and bounded skew collection."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from occams_beard.collectors.time import collect_time_state
from occams_beard.models import ClockSkewCheck


class TimeCollectionTests(unittest.TestCase):
    """Validate time collector behavior and degraded states."""

    @patch("occams_beard.collectors.time.current_platform", return_value="linux")
    @patch(
        "occams_beard.collectors.time._read_timezone_identifier",
        return_value=("America/Los_Angeles", "localtime-symlink"),
    )
    @patch(
        "occams_beard.collectors.time._observed_local_now",
        return_value=datetime.fromisoformat("2026-04-04T09:30:00-07:00"),
    )
    def test_collect_time_state_local_only_records_clock_and_timezone(
        self,
        _mock_now,
        _mock_timezone_identifier,
        _mock_platform,
    ) -> None:
        time_state, warnings = collect_time_state()

        self.assertEqual(time_state.local_time_iso, "2026-04-04T09:30:00-07:00")
        self.assertEqual(time_state.utc_time_iso, "2026-04-04T16:30:00+00:00")
        self.assertEqual(time_state.timezone_name, "UTC-07:00")
        self.assertEqual(time_state.timezone_identifier, "America/Los_Angeles")
        self.assertEqual(time_state.timezone_identifier_source, "localtime-symlink")
        self.assertEqual(time_state.utc_offset_minutes, -420)
        self.assertTrue(time_state.timezone_offset_consistent)
        self.assertEqual(time_state.skew_check.status, "not_run")
        self.assertEqual(warnings, [])

    @patch("occams_beard.collectors.time.current_platform", return_value="linux")
    @patch(
        "occams_beard.collectors.time._read_timezone_identifier",
        return_value=("America/Los_Angeles", "localtime-symlink"),
    )
    @patch(
        "occams_beard.collectors.time._observed_local_now",
        return_value=datetime.fromisoformat("2026-04-04T09:35:00-07:00"),
    )
    @patch(
        "occams_beard.collectors.time._perform_clock_skew_check",
        return_value=ClockSkewCheck(
            status="checked",
            reference_kind="https-date-header",
            reference_label="GitHub HTTPS response date",
            reference_url="https://github.com/",
            reference_time_iso="2026-04-04T16:34:10+00:00",
            observed_at_utc_iso="2026-04-04T16:35:00+00:00",
            skew_seconds=50.0,
            absolute_skew_seconds=50.0,
            duration_ms=120,
        ),
    )
    def test_collect_time_state_can_attach_clock_skew_result(
        self,
        _mock_skew_check,
        _mock_now,
        _mock_timezone_identifier,
        _mock_platform,
    ) -> None:
        progress_updates: list[int] = []

        time_state, warnings = collect_time_state(
            enable_skew_check=True,
            progress_callback=progress_updates.append,
        )

        self.assertEqual(progress_updates, [1, 2])
        self.assertEqual(time_state.skew_check.status, "checked")
        self.assertEqual(time_state.skew_check.absolute_skew_seconds, 50.0)
        self.assertEqual(warnings, [])

    @patch("occams_beard.collectors.time.current_platform", return_value="linux")
    @patch(
        "occams_beard.collectors.time._read_timezone_identifier",
        return_value=("America/Los_Angeles", "localtime-symlink"),
    )
    @patch(
        "occams_beard.collectors.time._observed_local_now",
        return_value=datetime.fromisoformat("2026-04-04T09:40:00-07:00"),
    )
    @patch(
        "occams_beard.collectors.time._perform_clock_skew_check",
        return_value=ClockSkewCheck(
            status="failed",
            reference_kind="https-date-header",
            reference_label="GitHub HTTPS response date",
            reference_url="https://github.com/",
            duration_ms=200,
            error="missing-date-header",
        ),
    )
    def test_collect_time_state_warns_when_skew_check_is_inconclusive(
        self,
        _mock_skew_check,
        _mock_now,
        _mock_timezone_identifier,
        _mock_platform,
    ) -> None:
        time_state, warnings = collect_time_state(enable_skew_check=True)

        self.assertEqual(time_state.skew_check.status, "failed")
        self.assertEqual([warning.code for warning in warnings], ["clock-skew-check-failed"])

    def test_collect_time_state_marks_utc_timezone_as_consistent(self) -> None:
        with (
            patch(
                "occams_beard.collectors.time.current_platform",
                return_value="linux",
            ),
            patch(
                "occams_beard.collectors.time._read_timezone_identifier",
                return_value=("UTC", "environment"),
            ),
            patch(
                "occams_beard.collectors.time._observed_local_now",
                return_value=datetime(2026, 4, 4, 16, 30, tzinfo=UTC),
            ),
        ):
            time_state, warnings = collect_time_state()

        self.assertTrue(time_state.timezone_offset_consistent)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
