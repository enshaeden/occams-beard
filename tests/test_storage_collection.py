"""Tests for storage collection behavior."""

from __future__ import annotations

import shutil
import unittest
from unittest.mock import patch

from occams_beard.collectors.storage import collect_storage_state
from occams_beard.utils.subprocess import CommandResult


class StorageCollectionTests(unittest.TestCase):
    """Validate storage mount filtering and warning behavior."""

    @patch("occams_beard.collectors.storage.current_platform", return_value="macos")
    @patch("occams_beard.collectors.storage.macos.read_storage_device_health", return_value=[])
    @patch("occams_beard.collectors.storage.shutil.disk_usage")
    @patch("occams_beard.collectors.storage.run_command")
    def test_collect_storage_state_filters_macos_pseudo_filesystems(
        self,
        mock_run_command,
        mock_disk_usage,
        _mock_storage_health,
        _mock_platform,
    ) -> None:
        mock_run_command.return_value = CommandResult(
            args=("df", "-kP"),
            returncode=0,
            stdout=(
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/disk3s1 100 50 50 50% /\n"
                "devfs 100 100 0 100% /dev\n"
                "/dev/disk3s5 100 20 80 20% /System/Volumes/Data\n"
                "/dev/disk7s1 100 100 0 100% "
                "/Library/Developer/CoreSimulator/Volumes/iOS_18A8395/data\n"
                "map auto_home 0 0 0 100% /System/Volumes/Data/home\n"
            ),
            stderr="",
            duration_ms=4,
        )
        usage_map = {
            "/": shutil._ntuple_diskusage(1000, 400, 600),
            "/System/Volumes/Data": shutil._ntuple_diskusage(2000, 800, 1200),
            "/System/Volumes/Data/home": shutil._ntuple_diskusage(3000, 900, 2100),
        }
        mock_disk_usage.side_effect = lambda path: usage_map[path]

        disks, storage_devices, warnings = collect_storage_state()

        self.assertEqual(
            [disk.path for disk in disks],
            ["/", "/System/Volumes/Data", "/System/Volumes/Data/home"],
        )
        self.assertEqual(storage_devices, [])
        self.assertEqual(warnings, [])
        self.assertEqual(
            [call.args[0] for call in mock_disk_usage.call_args_list],
            ["/", "/System/Volumes/Data", "/System/Volumes/Data/home"],
        )

    @patch("occams_beard.collectors.storage.current_platform", return_value="macos")
    @patch("occams_beard.collectors.storage.macos.read_storage_device_health", return_value=[])
    @patch("occams_beard.collectors.storage.shutil.disk_usage")
    @patch("occams_beard.collectors.storage.run_command")
    def test_discover_mount_points_uses_last_df_column_for_mount_path(
        self,
        mock_run_command,
        mock_disk_usage,
        _mock_storage_health,
        _mock_platform,
    ) -> None:
        mock_run_command.return_value = CommandResult(
            args=("df", "-kP"),
            returncode=0,
            stdout=(
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "map auto_home 0 0 0 100% /System/Volumes/Data/home\n"
            ),
            stderr="",
            duration_ms=4,
        )
        mock_disk_usage.return_value = shutil._ntuple_diskusage(3000, 900, 2100)

        disks, _storage_devices, warnings = collect_storage_state()

        self.assertEqual([disk.path for disk in disks], ["/System/Volumes/Data/home"])
        self.assertEqual(warnings, [])

    @patch("occams_beard.collectors.storage.current_platform", return_value="macos")
    @patch("occams_beard.collectors.storage.macos.read_storage_device_health", return_value=None)
    @patch("occams_beard.collectors.storage.shutil.disk_usage")
    @patch("occams_beard.collectors.storage.run_command")
    def test_collect_storage_state_warns_when_device_health_unavailable(
        self,
        mock_run_command,
        mock_disk_usage,
        _mock_storage_health,
        _mock_platform,
    ) -> None:
        mock_run_command.return_value = CommandResult(
            args=("df", "-kP"),
            returncode=0,
            stdout=(
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/disk3s1 100 50 50 50% /\n"
            ),
            stderr="",
            duration_ms=4,
        )
        mock_disk_usage.return_value = shutil._ntuple_diskusage(1000, 400, 600)

        disks, storage_devices, warnings = collect_storage_state()

        self.assertEqual([disk.path for disk in disks], ["/"])
        self.assertEqual(storage_devices, [])
        self.assertIn("storage-health-unavailable", [warning.code for warning in warnings])

    @patch("occams_beard.collectors.storage.current_platform", return_value="macos")
    @patch("occams_beard.collectors.storage.macos.read_storage_device_health", return_value=[])
    @patch("occams_beard.collectors.storage.shutil.disk_usage")
    @patch("occams_beard.collectors.storage.run_command")
    def test_collect_storage_state_reports_incremental_progress(
        self,
        mock_run_command,
        mock_disk_usage,
        _mock_storage_health,
        _mock_platform,
    ) -> None:
        mock_run_command.return_value = CommandResult(
            args=("df", "-kP"),
            returncode=0,
            stdout=(
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/disk3s1 100 50 50 50% /\n"
            ),
            stderr="",
            duration_ms=4,
        )
        mock_disk_usage.return_value = shutil._ntuple_diskusage(1000, 400, 600)
        progress_updates: list[int] = []

        collect_storage_state(progress_callback=progress_updates.append)

        self.assertEqual(progress_updates, [1, 2])


if __name__ == "__main__":
    unittest.main()
