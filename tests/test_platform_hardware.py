"""Tests for platform-specific hardware health helpers."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from occams_beard.platform import macos, windows
from occams_beard.utils.subprocess import CommandResult


class MacosHardwareHelperTests(unittest.TestCase):
    """Validate macOS battery and storage-device parsing."""

    @patch("occams_beard.platform.macos.run_command")
    def test_read_battery_snapshot_parses_system_profiler_and_pmset(self, mock_run_command) -> None:
        mock_run_command.side_effect = [
            CommandResult(
                args=("system_profiler", "SPPowerDataType"),
                returncode=0,
                stdout=(
                    "Power:\n"
                    "    Battery Information:\n"
                    "      Cycle Count: 126\n"
                    "      Condition: Service Recommended\n"
                    "      Maximum Capacity: 79%\n"
                ),
                stderr="",
                duration_ms=20,
            ),
            CommandResult(
                args=("pmset", "-g", "batt"),
                returncode=0,
                stdout=(
                    "Now drawing from 'AC Power'\n"
                    " -InternalBattery-0\t91%; charging; 0:22 remaining present: true\n"
                ),
                stderr="",
                duration_ms=4,
            ),
        ]

        snapshot = macos.read_battery_snapshot()

        self.assertEqual(
            snapshot,
            {
                "present": True,
                "cycle_count": 126,
                "condition": "Service Recommended",
                "health_percent": 79.0,
                "charge_percent": 91,
                "status": "charging",
            },
        )

    @patch("occams_beard.platform.macos.run_command")
    def test_read_storage_device_health_parses_whole_disk_entries(self, mock_run_command) -> None:
        mock_run_command.return_value = CommandResult(
            args=("diskutil", "info", "-all"),
            returncode=0,
            stdout=(
                "   Device Identifier:        disk0\n"
                "   Device / Media Name:      APPLE SSD AP1024Z\n"
                "   Part of Whole:            disk0\n"
                "   Protocol:                 PCI-Express\n"
                "   Solid State:              Yes\n"
                "   SMART Status:             Verified\n"
                "\n"
                "   Device Identifier:        disk0s1\n"
                "   Part of Whole:            disk0\n"
                "   Protocol:                 PCI-Express\n"
                "   SMART Status:             Verified\n"
            ),
            stderr="",
            duration_ms=10,
        )

        devices = macos.read_storage_device_health()

        self.assertEqual(
            devices,
            [
                {
                    "device_id": "disk0",
                    "model": "APPLE SSD AP1024Z",
                    "protocol": "PCI-Express",
                    "medium": "SSD",
                    "health_status": "Verified",
                    "operational_status": None,
                }
            ],
        )


class WindowsHardwareHelperTests(unittest.TestCase):
    """Validate Windows hardware-health parsing."""

    @patch("occams_beard.platform.windows.run_command")
    def test_read_storage_device_health_parses_json_list(self, mock_run_command) -> None:
        mock_run_command.return_value = CommandResult(
            args=("powershell", "-NoProfile", "-Command", "Get-PhysicalDisk"),
            returncode=0,
            stdout=json.dumps(
                [
                    {
                        "DeviceId": 0,
                        "FriendlyName": "NVMe Samsung SSD",
                        "HealthStatus": "Healthy",
                        "OperationalStatus": "OK",
                        "MediaType": "SSD",
                    }
                ]
            ),
            stderr="",
            duration_ms=8,
        )

        devices = windows.read_storage_device_health()

        self.assertEqual(
            devices,
            [
                {
                    "device_id": "NVMe Samsung SSD",
                    "model": "NVMe Samsung SSD",
                    "protocol": None,
                    "medium": "SSD",
                    "health_status": "Healthy",
                    "operational_status": "OK",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
