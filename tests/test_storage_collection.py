"""Tests for storage collection behavior."""

from __future__ import annotations

import shutil
import unittest
from unittest.mock import patch

from occams_beard.collectors.storage import collect_storage_state
from occams_beard.storage_policy import classify_disk_pressure, distinct_capacity_groups
from occams_beard.utils.subprocess import CommandResult


class StorageCollectionTests(unittest.TestCase):
    """Validate storage mount filtering and warning behavior."""

    def test_classify_disk_pressure_uses_correct_free_space_semantics(self) -> None:
        self.assertEqual(
            classify_disk_pressure(total_bytes=100, free_bytes=96, role_hint="system"),
            "normal",
        )
        self.assertEqual(
            classify_disk_pressure(total_bytes=100, free_bytes=4, role_hint="system"),
            "critical",
        )

    @patch("occams_beard.collectors.storage.current_platform", return_value="linux")
    @patch("occams_beard.collectors.storage.linux.read_storage_device_health", return_value=[])
    @patch("occams_beard.collectors.storage.shutil.disk_usage")
    @patch("occams_beard.collectors.storage.run_command")
    def test_collect_storage_state_filters_linux_pseudo_filesystems(
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
                "/dev/root 100 92 8 92% /\n"
                "tmpfs 100 10 90 10% /run\n"
                "tmpfs 100 5 95 5% /dev/shm\n"
                "/dev/nvme0n1p2 100 40 60 40% /home\n"
            ),
            stderr="",
            duration_ms=4,
        )
        usage_map = {
            "/": shutil._ntuple_diskusage(
                100 * 1024**3,
                92 * 1024**3,
                8 * 1024**3,
            ),
            "/home": shutil._ntuple_diskusage(
                200 * 1024**3,
                80 * 1024**3,
                120 * 1024**3,
            ),
        }
        mock_disk_usage.side_effect = lambda path: usage_map[path]

        disks, storage_devices, warnings = collect_storage_state()

        self.assertEqual([disk.path for disk in disks], ["/", "/home"])
        self.assertEqual(disks[0].pressure_level, "low")
        self.assertEqual(disks[0].role_hint, "system")
        self.assertEqual(disks[1].role_hint, "user_data")
        self.assertEqual(storage_devices, [])
        self.assertEqual(warnings, [])

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
        self.assertEqual(disks[0].role_hint, "system")
        self.assertEqual(disks[0].free_percent, 60.0)
        self.assertEqual(disks[1].role_hint, "user_data")
        self.assertEqual(disks[2].role_hint, "ephemeral")
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
    def test_collect_storage_state_marks_macos_helper_volumes_as_auxiliary_diagnostics(
        self,
        mock_run_command,
        mock_disk_usage,
        _mock_storage_health,
        _mock_platform,
    ) -> None:
        gib = 1024**3
        mock_run_command.return_value = CommandResult(
            args=("df", "-kP"),
            returncode=0,
            stdout=(
                "Filesystem 1024-blocks Used Available Capacity Mounted on\n"
                "/dev/disk3s1 100 30 70 30% /\n"
                "/dev/disk3s5 100 30 70 30% /System/Volumes/Data\n"
                "/dev/disk4s2 100 4 96 4% /System/Volumes/Hardware\n"
                "/dev/disk4s3 100 4 96 4% /System/Volumes/iSCPreboot\n"
                "/dev/disk4s4 100 4 96 4% /System/Volumes/xarts\n"
            ),
            stderr="",
            duration_ms=4,
        )
        usage_map = {
            "/": shutil._ntuple_diskusage(500 * gib, 152 * gib, 348 * gib),
            "/System/Volumes/Data": shutil._ntuple_diskusage(500 * gib, 152 * gib, 348 * gib),
            "/System/Volumes/Hardware": shutil._ntuple_diskusage(
                512 * 1024**2,
                20 * 1024**2,
                492 * 1024**2,
            ),
            "/System/Volumes/iSCPreboot": shutil._ntuple_diskusage(
                512 * 1024**2,
                20 * 1024**2,
                492 * 1024**2,
            ),
            "/System/Volumes/xarts": shutil._ntuple_diskusage(
                512 * 1024**2,
                20 * 1024**2,
                492 * 1024**2,
            ),
        }
        mock_disk_usage.side_effect = lambda path: usage_map[path]

        disks, storage_devices, warnings = collect_storage_state()

        self.assertEqual(
            [disk.path for disk in disks],
            [
                "/",
                "/System/Volumes/Data",
                "/System/Volumes/Hardware",
                "/System/Volumes/iSCPreboot",
                "/System/Volumes/xarts",
            ],
        )
        self.assertEqual([disk.role_hint for disk in disks[:2]], ["system", "user_data"])
        self.assertEqual(
            [disk.role_hint for disk in disks[2:]],
            ["auxiliary", "auxiliary", "auxiliary"],
        )
        self.assertTrue(all(disk.pressure_level == "normal" for disk in disks))
        self.assertEqual(storage_devices, [])
        self.assertEqual(warnings, [])

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

    @patch("occams_beard.collectors.storage.current_platform", return_value="macos")
    @patch("occams_beard.collectors.storage.macos.read_storage_device_health", return_value=[])
    @patch("occams_beard.collectors.storage.shutil.disk_usage")
    @patch("occams_beard.collectors.storage.run_command")
    def test_zero_capacity_pseudo_mount_is_retained_but_not_counted_in_capacity_groups(
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
                "/dev/disk3s5 100 20 80 20% /System/Volumes/Data\n"
                "map auto_home 0 0 0 100% /System/Volumes/Data/home\n"
            ),
            stderr="",
            duration_ms=4,
        )
        usage_map = {
            "/System/Volumes/Data": shutil._ntuple_diskusage(2000, 800, 1200),
            "/System/Volumes/Data/home": shutil._ntuple_diskusage(0, 0, 0),
        }
        mock_disk_usage.side_effect = lambda path: usage_map[path]

        disks, _storage_devices, warnings = collect_storage_state()

        self.assertEqual(
            [disk.path for disk in disks],
            ["/System/Volumes/Data", "/System/Volumes/Data/home"],
        )
        self.assertEqual(disks[1].pressure_level, "unknown")
        self.assertIsNone(disks[1].free_percent)
        self.assertEqual(len(distinct_capacity_groups(disks)), 1)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
