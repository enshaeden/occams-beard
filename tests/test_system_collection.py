"""Tests for system resource collection behavior."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from occams_beard.collectors.system import collect_resource_state


class SystemCollectionTests(unittest.TestCase):
    """Validate CPU, memory, and battery collection behavior."""

    @patch("occams_beard.collectors.system.current_platform", return_value="linux")
    @patch(
        "occams_beard.collectors.system.linux.read_battery_snapshot",
        return_value={
            "present": True,
            "charge_percent": 94,
            "status": "Discharging",
            "cycle_count": 120,
            "condition": "Good",
            "health_percent": 98.0,
        },
    )
    @patch(
        "occams_beard.collectors.system.linux.read_memory_snapshot",
        return_value={
            "total_bytes": 1000,
            "available_bytes": 500,
            "free_bytes": 400,
        },
    )
    @patch("occams_beard.collectors.system.os.getloadavg", return_value=(0.5, 0.4, 0.3), create=True)
    @patch("occams_beard.collectors.system.os.cpu_count", return_value=8)
    def test_collect_resource_state_includes_battery_facts(
        self,
        _mock_cpu_count,
        _mock_loadavg,
        _mock_memory,
        _mock_battery,
        _mock_platform,
    ) -> None:
        cpu, memory, battery, warnings = collect_resource_state()

        self.assertEqual(cpu.logical_cpus, 8)
        self.assertEqual(memory.pressure_level, "normal")
        self.assertIsNotNone(battery)
        self.assertTrue(battery.present)
        self.assertEqual(battery.charge_percent, 94)
        self.assertEqual(battery.condition, "Good")
        self.assertEqual(warnings, [])

    @patch("occams_beard.collectors.system.current_platform", return_value="macos")
    @patch("occams_beard.collectors.system.macos.read_battery_snapshot", return_value=None)
    @patch(
        "occams_beard.collectors.system.macos.read_memory_snapshot",
        return_value={
            "total_bytes": 1000,
            "available_bytes": 100,
            "free_bytes": 50,
        },
    )
    @patch("occams_beard.collectors.system.os.getloadavg", return_value=(1.0, 0.8, 0.6), create=True)
    @patch("occams_beard.collectors.system.os.cpu_count", return_value=4)
    def test_collect_resource_state_warns_when_battery_is_unavailable(
        self,
        _mock_cpu_count,
        _mock_loadavg,
        _mock_memory,
        _mock_battery,
        _mock_platform,
    ) -> None:
        _cpu, _memory, battery, warnings = collect_resource_state()

        self.assertIsNone(battery)
        self.assertIn("battery-unavailable", [warning.code for warning in warnings])

    @patch("occams_beard.collectors.system.current_platform", return_value="linux")
    @patch("occams_beard.collectors.system.linux.read_battery_snapshot", return_value=None)
    @patch(
        "occams_beard.collectors.system.linux.read_memory_snapshot",
        return_value={
            "total_bytes": 1000,
            "available_bytes": 500,
            "free_bytes": 400,
        },
    )
    @patch("occams_beard.collectors.system.os.getloadavg", return_value=(0.5, 0.4, 0.3), create=True)
    @patch("occams_beard.collectors.system.os.cpu_count", return_value=8)
    def test_collect_resource_state_reports_incremental_progress(
        self,
        _mock_cpu_count,
        _mock_loadavg,
        _mock_memory,
        _mock_battery,
        _mock_platform,
    ) -> None:
        progress_updates: list[int] = []

        collect_resource_state(progress_callback=progress_updates.append)

        self.assertEqual(progress_updates, [1, 2])

    @patch("occams_beard.collectors.system.current_platform", return_value="windows")
    @patch("occams_beard.collectors.system.windows.read_battery_snapshot", return_value={"present": False})
    @patch(
        "occams_beard.collectors.system.windows.read_memory_snapshot",
        return_value={
            "total_bytes": 16 * 1024**3,
            "available_bytes": 8 * 1024**3,
            "free_bytes": 8 * 1024**3,
        },
    )
    @patch("occams_beard.collectors.system.os.cpu_count", return_value=8)
    def test_collect_resource_state_avoids_windows_unsupported_warnings_when_facts_exist(
        self,
        _mock_cpu_count,
        _mock_memory,
        _mock_battery,
        _mock_platform,
    ) -> None:
        cpu, memory, battery, warnings = collect_resource_state()

        self.assertEqual(cpu.logical_cpus, 8)
        self.assertEqual(memory.pressure_level, "normal")
        self.assertIsNotNone(battery)
        self.assertFalse(battery.present)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
