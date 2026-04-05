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

    def test_read_uptime_seconds_uses_kernel_tick_counter(self) -> None:
        with patch("occams_beard.platform.windows.ctypes.windll", create=True) as mock_windll:
            mock_windll.kernel32.GetTickCount64.return_value = 12_345_000

            uptime_seconds = windows.read_uptime_seconds()

        self.assertEqual(uptime_seconds, 12_345)

    def test_read_memory_snapshot_uses_global_memory_status(self) -> None:
        with patch("occams_beard.platform.windows.ctypes.windll", create=True) as mock_windll:
            def populate_memory_status(pointer) -> int:
                status = pointer._obj
                status.ullTotalPhys = 32 * 1024**3
                status.ullAvailPhys = 20 * 1024**3
                return 1

            mock_windll.kernel32.GlobalMemoryStatusEx.side_effect = populate_memory_status

            snapshot = windows.read_memory_snapshot()

        self.assertEqual(
            snapshot,
            {
                "total_bytes": 32 * 1024**3,
                "available_bytes": 20 * 1024**3,
                "free_bytes": 20 * 1024**3,
                "swap_total_bytes": None,
                "swap_free_bytes": None,
                "swap_used_bytes": None,
                "committed_bytes": None,
                "commit_limit_bytes": None,
            },
        )

    def test_read_battery_snapshot_uses_power_status_and_detects_no_battery(self) -> None:
        with patch("occams_beard.platform.windows.ctypes.windll", create=True) as mock_windll:
            def populate_power_status(pointer) -> int:
                status = pointer._obj
                status.ACLineStatus = 1
                status.BatteryFlag = 128
                status.BatteryLifePercent = 255
                return 1

            mock_windll.kernel32.GetSystemPowerStatus.side_effect = populate_power_status

            snapshot = windows.read_battery_snapshot()

        self.assertEqual(snapshot, {"present": False})

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

    @patch("occams_beard.platform.windows.run_command")
    def test_read_timezone_identifier_uses_tzutil(self, mock_run_command) -> None:
        mock_run_command.return_value = CommandResult(
            args=("tzutil", "/g"),
            returncode=0,
            stdout="Pacific Standard Time\n",
            stderr="",
            duration_ms=4,
        )

        identifier = windows.read_timezone_identifier()

        self.assertEqual(identifier, "Pacific Standard Time")

    @patch("occams_beard.platform.windows.run_command")
    def test_read_resolvers_falls_back_to_ipconfig_when_powershell_is_denied(
        self, mock_run_command
    ) -> None:
        mock_run_command.side_effect = [
            CommandResult(
                args=(
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-DnsClientServerAddress | Select-Object -ExpandProperty ServerAddresses",
                ),
                returncode=1,
                stdout="",
                stderr="Access denied",
                duration_ms=10,
            ),
            CommandResult(
                args=("ipconfig", "/all"),
                returncode=0,
                stdout=(
                    "Ethernet adapter Ethernet:\n\n"
                    "   DNS Servers . . . . . . . . . . . : 10.0.0.2\n"
                    "                                       1.1.1.1\n"
                ),
                stderr="",
                duration_ms=12,
            ),
        ]

        resolvers = windows.read_resolvers()

        self.assertEqual(resolvers, ["10.0.0.2", "1.1.1.1"])


if __name__ == "__main__":
    unittest.main()
