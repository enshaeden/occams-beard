"""Tests for the repo-root launch bootstrap."""

from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from occams_beard import root_launcher


class RootLauncherTests(unittest.TestCase):
    """Validate cross-platform repo-root launch behavior."""

    def test_project_python_candidate_uses_windows_virtualenv_path(self) -> None:
        project_root = Path("C:/repo")

        with patch("occams_beard.root_launcher.os.name", "nt"):
            candidate = root_launcher._project_python_candidate(project_root)

        self.assertEqual(candidate, project_root / ".venv" / "Scripts" / "python.exe")

    def test_project_python_candidate_uses_posix_virtualenv_path(self) -> None:
        project_root = Path("/repo")

        with patch("occams_beard.root_launcher.os.name", "posix"):
            candidate = root_launcher._project_python_candidate(project_root)

        self.assertEqual(candidate, project_root / ".venv" / "bin" / "python3")

    def test_prepend_pythonpath_avoids_duplicate_src_path(self) -> None:
        src_path = str(Path("/repo/src"))
        current = os.pathsep.join([src_path, str(Path("/repo/tests"))])

        combined = root_launcher._prepend_pythonpath(src_path, current)

        self.assertEqual(combined, current)

    @patch("occams_beard.root_launcher.subprocess.run")
    @patch("occams_beard.root_launcher._resolve_project_python")
    @patch("occams_beard.root_launcher._bootstrap_local_environment")
    @patch("occams_beard.root_launcher._launcher_dependencies_ready", return_value=False)
    @patch("occams_beard.root_launcher._resolve_bootstrap_python")
    def test_bootstrap_and_launch_bootstraps_when_dependencies_are_missing(
        self,
        mock_resolve_bootstrap_python,
        _mock_dependencies_ready,
        mock_bootstrap_local_environment,
        mock_resolve_project_python,
        mock_subprocess_run,
    ) -> None:
        project_root = Path("/repo")
        bootstrap_python = project_root / ".venv" / "bin" / "python3"
        launcher_python = project_root / ".venv" / "bin" / "python3"
        mock_resolve_bootstrap_python.return_value = bootstrap_python
        mock_resolve_project_python.return_value = launcher_python
        mock_subprocess_run.return_value = subprocess.CompletedProcess(args=[], returncode=0)

        result = root_launcher.bootstrap_and_launch(project_root, ["--no-browser"])

        self.assertEqual(result, 0)
        mock_bootstrap_local_environment.assert_called_once_with(project_root, bootstrap_python)
        mock_subprocess_run.assert_called_once()
        command = mock_subprocess_run.call_args.args[0]
        self.assertEqual(
            command,
            [str(launcher_python), "-m", "occams_beard.launcher", "--no-browser"],
        )

    @patch("occams_beard.root_launcher.bootstrap_and_launch", return_value=0)
    @patch("occams_beard.root_launcher._resolve_project_root", return_value=Path("/repo"))
    def test_main_forwards_unknown_launcher_flags_without_requiring_separator(
        self,
        _mock_resolve_project_root,
        mock_bootstrap_and_launch,
    ) -> None:
        result = root_launcher.main(["--project-root", "/repo", "--no-browser"])

        self.assertEqual(result, 0)
        mock_bootstrap_and_launch.assert_called_once_with(Path("/repo"), ["--no-browser"])


if __name__ == "__main__":
    unittest.main()
