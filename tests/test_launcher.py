"""Tests for the operator launcher."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from occams_beard.launcher import (
    BrowserPresenceTracker,
    LauncherDependencyError,
    OperatorLauncherConfig,
    _build_browser_url,
    _load_web_dependencies,
    _make_server_with_fallback,
    _write_ready_file,
    launch_operator_interface,
    main,
)

TEST_TEMP_ROOT = Path(__file__).resolve().parent / ".tmp"


class LauncherTests(unittest.TestCase):
    """Validate browser URL shaping and launcher orchestration."""

    def test_browser_presence_tracker_waits_for_close_grace_period_before_shutdown(self) -> None:
        current_time = 100.0

        def now() -> float:
            return current_time

        tracker = BrowserPresenceTracker(
            idle_timeout_seconds=90.0,
            close_grace_seconds=5.0,
            startup_timeout_seconds=60.0,
            now=now,
        )
        tracker.record_heartbeat()
        tracker.record_page_closing()

        current_time += 4.9
        self.assertFalse(tracker.should_shutdown())

        current_time += 0.2
        self.assertTrue(tracker.should_shutdown())

    def test_browser_presence_tracker_stops_when_browser_never_checks_in(self) -> None:
        current_time = 10.0

        def now() -> float:
            return current_time

        tracker = BrowserPresenceTracker(
            startup_timeout_seconds=3.0,
            now=now,
        )

        current_time += 2.9
        self.assertFalse(tracker.should_shutdown())

        current_time += 0.2
        self.assertTrue(tracker.should_shutdown())

    def test_build_browser_url_rewrites_wildcard_host_for_local_browser(self) -> None:
        self.assertEqual(_build_browser_url("0.0.0.0", 5000), "http://127.0.0.1:5000")

    def test_write_ready_file_persists_exact_url(self) -> None:
        TEST_TEMP_ROOT.mkdir(exist_ok=True)
        ready_path = TEST_TEMP_ROOT / "ready-file-test.txt"
        if ready_path.exists():
            ready_path.unlink()
        self.addCleanup(lambda: ready_path.unlink(missing_ok=True))

        _write_ready_file(str(ready_path), "http://127.0.0.1:5010")

        self.assertEqual(ready_path.read_text(encoding="utf-8"), "http://127.0.0.1:5010\n")

    @patch("occams_beard.launcher.launch_operator_interface", return_value=0)
    def test_main_delegates_to_launch_operator_interface(
        self, mock_launch_operator_interface
    ) -> None:
        result = main(["--no-browser", "--port", "5013"])

        self.assertEqual(result, 0)
        mock_launch_operator_interface.assert_called_once()
        config = mock_launch_operator_interface.call_args.args[0]
        self.assertEqual(config.port, 5013)
        self.assertFalse(config.open_browser)

    def test_make_server_with_fallback_prefers_requested_port_when_available(self) -> None:
        make_server = MagicMock(return_value=MagicMock(server_port=5000))

        server = _make_server_with_fallback(make_server, "127.0.0.1", 5000, object())

        self.assertEqual(server.server_port, 5000)
        make_server.assert_called_once()

    @patch("occams_beard.launcher.LOGGER")
    def test_make_server_with_fallback_chooses_ephemeral_port_when_requested_port_is_busy(
        self,
        mock_logger,
    ) -> None:
        preferred_server_error = OSError(48, "Address already in use")
        fallback_server = MagicMock(server_port=5010)
        make_server = MagicMock(side_effect=[preferred_server_error, fallback_server])

        server = _make_server_with_fallback(make_server, "127.0.0.1", 5000, object())

        self.assertEqual(server.server_port, 5010)
        self.assertEqual(make_server.call_count, 2)
        self.assertEqual(make_server.call_args_list[1].args[1], 0)
        mock_logger.warning.assert_called_once()

    @patch("occams_beard.launcher.importlib.import_module")
    def test_load_web_dependencies_raises_clear_error_when_dependency_missing(
        self,
        mock_import_module,
    ) -> None:
        mock_import_module.side_effect = ModuleNotFoundError("No module named 'werkzeug'")

        with self.assertRaises(LauncherDependencyError) as context:
            _load_web_dependencies()

        self.assertIn("dependencies are missing", str(context.exception))

    @patch("occams_beard.launcher._open_browser")
    @patch("occams_beard.launcher._wait_for_server", return_value=True)
    @patch("occams_beard.launcher._load_web_dependencies")
    @patch("builtins.print")
    def test_launch_operator_interface_starts_server_and_opens_browser(
        self,
        _mock_print,
        mock_load_web_dependencies,
        _mock_wait,
        mock_open_browser,
    ) -> None:
        server = MagicMock()
        server.server_port = 5010
        mock_load_web_dependencies.return_value = (
            MagicMock(return_value=object()),
            MagicMock(return_value=server),
        )
        server.serve_forever.side_effect = None

        with patch("occams_beard.launcher.threading.Thread") as mock_thread_class:
            thread = MagicMock()
            thread.is_alive.side_effect = [False]
            mock_thread_class.return_value = thread

            result = launch_operator_interface(OperatorLauncherConfig())

        self.assertEqual(result, 0)
        mock_load_web_dependencies.assert_called_once()
        thread.start.assert_called_once()
        mock_open_browser.assert_called_once_with("http://127.0.0.1:5010")
        server.shutdown.assert_called_once()
        thread.join.assert_called_once_with(timeout=5)

    @patch("occams_beard.launcher._open_browser")
    @patch("occams_beard.launcher._wait_for_server", return_value=True)
    @patch("occams_beard.launcher._load_web_dependencies")
    @patch("builtins.print")
    def test_launch_operator_interface_writes_ready_file_with_bound_url(
        self,
        _mock_print,
        mock_load_web_dependencies,
        _mock_wait,
        mock_open_browser,
    ) -> None:
        server = MagicMock()
        server.server_port = 5012
        mock_load_web_dependencies.return_value = (
            MagicMock(return_value=object()),
            MagicMock(return_value=server),
        )

        TEST_TEMP_ROOT.mkdir(exist_ok=True)
        ready_path = TEST_TEMP_ROOT / "launch-ready-file-test.txt"
        if ready_path.exists():
            ready_path.unlink()
        self.addCleanup(lambda: ready_path.unlink(missing_ok=True))
        with patch("occams_beard.launcher.threading.Thread") as mock_thread_class:
            thread = MagicMock()
            thread.is_alive.side_effect = [False]
            mock_thread_class.return_value = thread

            result = launch_operator_interface(OperatorLauncherConfig(ready_file=str(ready_path)))

        ready_text = ready_path.read_text(encoding="utf-8")

        self.assertEqual(result, 0)
        self.assertEqual(ready_text, "http://127.0.0.1:5012\n")
        mock_open_browser.assert_called_once_with("http://127.0.0.1:5012")

    @patch("occams_beard.launcher._wait_for_server", return_value=False)
    @patch("occams_beard.launcher._load_web_dependencies")
    @patch("occams_beard.launcher.LOGGER")
    @patch("builtins.print")
    def test_launch_operator_interface_returns_non_zero_when_server_never_becomes_ready(
        self,
        _mock_print,
        _mock_logger,
        mock_load_web_dependencies,
        _mock_wait,
    ) -> None:
        server = MagicMock()
        server.server_port = 5011
        mock_load_web_dependencies.return_value = (
            MagicMock(return_value=object()),
            MagicMock(return_value=server),
        )

        with patch("occams_beard.launcher.threading.Thread") as mock_thread_class:
            thread = MagicMock()
            mock_thread_class.return_value = thread

            result = launch_operator_interface(
                OperatorLauncherConfig(open_browser=False, wait_timeout_seconds=0.1)
            )

        self.assertEqual(result, 1)
        thread.start.assert_called_once()
        server.shutdown.assert_called_once()
        thread.join.assert_called_once_with(timeout=5)

    @patch("occams_beard.launcher.LOGGER")
    @patch(
        "occams_beard.launcher._load_web_dependencies",
        side_effect=LauncherDependencyError("missing deps"),
    )
    def test_launch_operator_interface_returns_non_zero_when_dependencies_are_missing(
        self,
        mock_load_web_dependencies,
        mock_logger,
    ) -> None:
        result = launch_operator_interface(OperatorLauncherConfig())

        self.assertEqual(result, 1)
        mock_load_web_dependencies.assert_called_once()
        mock_logger.error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
