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
            "swap_total_bytes": 200,
            "swap_free_bytes": 150,
            "swap_used_bytes": 50,
            "committed_bytes": 600,
            "commit_limit_bytes": 1200,
        },
    )
    @patch(
        "occams_beard.collectors.system.linux.read_process_snapshot",
        return_value=[
            {
                "name": "Google Chrome",
                "cpu_percent_estimate": 62.0,
                "memory_bytes": 900 * 1024**2,
            },
            {"name": "Code", "cpu_percent_estimate": 18.0, "memory_bytes": 700 * 1024**2},
            {"name": "dockerd", "cpu_percent_estimate": 12.0, "memory_bytes": 600 * 1024**2},
        ],
    )
    @patch(
        "occams_beard.collectors.system.os.getloadavg",
        return_value=(0.5, 0.4, 0.3),
        create=True,
    )
    @patch("occams_beard.collectors.system.os.cpu_count", return_value=8)
    def test_collect_resource_state_includes_battery_facts(
        self,
        _mock_cpu_count,
        _mock_loadavg,
        _mock_processes,
        _mock_memory,
        _mock_battery,
        _mock_platform,
    ) -> None:
        cpu, memory, battery, process_snapshot, warnings = collect_resource_state()

        self.assertEqual(cpu.logical_cpus, 8)
        self.assertEqual(cpu.saturation_level, "normal")
        self.assertEqual(memory.pressure_level, "normal")
        self.assertEqual(memory.available_percent, 50.0)
        self.assertEqual(memory.commit_pressure_level, "normal")
        self.assertIsNotNone(battery)
        self.assertTrue(battery.present)
        self.assertEqual(battery.charge_percent, 94)
        self.assertEqual(battery.condition, "Good")
        self.assertIsNotNone(process_snapshot)
        self.assertEqual(process_snapshot.high_cpu_process_count, 1)
        self.assertEqual(process_snapshot.high_memory_process_count, 3)
        self.assertEqual(
            [item.category for item in process_snapshot.top_categories],
            ["browser", "ide", "container_runtime"],
        )
        self.assertEqual(warnings, [])

    @patch("occams_beard.collectors.system.current_platform", return_value="macos")
    @patch("occams_beard.collectors.system.macos.read_battery_snapshot", return_value=None)
    @patch(
        "occams_beard.collectors.system.macos.read_memory_snapshot",
        return_value={
            "total_bytes": 1000,
            "available_bytes": 100,
            "free_bytes": 50,
            "swap_total_bytes": 500,
            "swap_free_bytes": 100,
            "swap_used_bytes": 400,
            "committed_bytes": None,
            "commit_limit_bytes": None,
        },
    )
    @patch("occams_beard.collectors.system.macos.read_process_snapshot", return_value=None)
    @patch(
        "occams_beard.collectors.system.os.getloadavg",
        return_value=(1.0, 0.8, 0.6),
        create=True,
    )
    @patch("occams_beard.collectors.system.os.cpu_count", return_value=4)
    def test_collect_resource_state_warns_when_battery_is_unavailable(
        self,
        _mock_cpu_count,
        _mock_loadavg,
        _mock_processes,
        _mock_memory,
        _mock_battery,
        _mock_platform,
    ) -> None:
        _cpu, memory, battery, process_snapshot, warnings = collect_resource_state()

        self.assertIsNone(battery)
        self.assertIsNone(process_snapshot)
        self.assertEqual(memory.swap_used_bytes, 400)
        self.assertIn("battery-unavailable", [warning.code for warning in warnings])
        self.assertIn("process-snapshot-unavailable", [warning.code for warning in warnings])

    @patch("occams_beard.collectors.system.current_platform", return_value="linux")
    @patch("occams_beard.collectors.system.linux.read_battery_snapshot", return_value=None)
    @patch(
        "occams_beard.collectors.system.linux.read_memory_snapshot",
        return_value={
            "total_bytes": 1000,
            "available_bytes": 500,
            "free_bytes": 400,
            "swap_total_bytes": None,
            "swap_free_bytes": None,
            "swap_used_bytes": None,
            "committed_bytes": None,
            "commit_limit_bytes": None,
        },
    )
    @patch("occams_beard.collectors.system.linux.read_process_snapshot", return_value=[])
    @patch(
        "occams_beard.collectors.system.os.getloadavg",
        return_value=(0.5, 0.4, 0.3),
        create=True,
    )
    @patch("occams_beard.collectors.system.os.cpu_count", return_value=8)
    def test_collect_resource_state_reports_incremental_progress(
        self,
        _mock_cpu_count,
        _mock_loadavg,
        _mock_processes,
        _mock_memory,
        _mock_battery,
        _mock_platform,
    ) -> None:
        progress_updates: list[int] = []

        collect_resource_state(progress_callback=progress_updates.append)

        self.assertEqual(progress_updates, [1, 2, 3])

    @patch("occams_beard.collectors.system.current_platform", return_value="windows")
    @patch(
        "occams_beard.collectors.system.windows.read_battery_snapshot",
        return_value={"present": False},
    )
    @patch(
        "occams_beard.collectors.system.windows.read_memory_snapshot",
        return_value={
            "total_bytes": 16 * 1024**3,
            "available_bytes": 8 * 1024**3,
            "free_bytes": 8 * 1024**3,
            "swap_total_bytes": None,
            "swap_free_bytes": None,
            "swap_used_bytes": None,
            "committed_bytes": None,
            "commit_limit_bytes": None,
        },
    )
    @patch(
        "occams_beard.collectors.system.windows.read_process_snapshot",
        return_value=[
            {
                "name": "Code",
                "cpu_percent_estimate": None,
                "memory_bytes": 600 * 1024**2,
            }
        ],
    )
    @patch("occams_beard.collectors.system.os.cpu_count", return_value=8)
    def test_collect_resource_state_avoids_windows_unsupported_warnings_when_facts_exist(
        self,
        _mock_cpu_count,
        _mock_processes,
        _mock_memory,
        _mock_battery,
        _mock_platform,
    ) -> None:
        cpu, memory, battery, process_snapshot, warnings = collect_resource_state()

        self.assertEqual(cpu.logical_cpus, 8)
        self.assertEqual(memory.pressure_level, "normal")
        self.assertIsNotNone(battery)
        self.assertFalse(battery.present)
        self.assertIsNotNone(process_snapshot)
        self.assertEqual(process_snapshot.top_categories[0].category, "ide")
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
