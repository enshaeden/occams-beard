"""Tests for storage collection behavior."""

from __future__ import annotations

import shutil
import unittest
from unittest.mock import patch

from endpoint_diagnostics_lab.collectors.storage import collect_storage_state
from endpoint_diagnostics_lab.utils.subprocess import CommandResult


class StorageCollectionTests(unittest.TestCase):
    """Validate storage mount filtering and warning behavior."""

    @patch("endpoint_diagnostics_lab.collectors.storage.current_platform", return_value="macos")
    @patch("endpoint_diagnostics_lab.collectors.storage.shutil.disk_usage")
    @patch("endpoint_diagnostics_lab.collectors.storage.run_command")
    def test_collect_storage_state_filters_macos_pseudo_filesystems(
        self,
        mock_run_command,
        mock_disk_usage,
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
            ),
            stderr="",
            duration_ms=4,
        )
        usage_map = {
            "/": shutil._ntuple_diskusage(1000, 400, 600),
            "/System/Volumes/Data": shutil._ntuple_diskusage(2000, 800, 1200),
        }
        mock_disk_usage.side_effect = lambda path: usage_map[path]

        disks, warnings = collect_storage_state()

        self.assertEqual([disk.path for disk in disks], ["/", "/System/Volumes/Data"])
        self.assertEqual(warnings, [])
        self.assertEqual(
            [call.args[0] for call in mock_disk_usage.call_args_list],
            ["/", "/System/Volumes/Data"],
        )


if __name__ == "__main__":
    unittest.main()
