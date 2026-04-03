"""Launcher for the local operator interface."""

from __future__ import annotations

import argparse
import importlib
import logging
import socket
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)
DEFAULT_WAIT_TIMEOUT_SECONDS = 10.0
DEFAULT_BROWSER_HEARTBEAT_INTERVAL_SECONDS = 15.0
DEFAULT_BROWSER_IDLE_TIMEOUT_SECONDS = 90.0
DEFAULT_BROWSER_CLOSE_GRACE_SECONDS = 5.0
DEFAULT_BROWSER_STARTUP_TIMEOUT_SECONDS = 60.0


class BrowserPresenceTracker:
    """Track whether the launcher-opened browser page is still present."""

    def __init__(
        self,
        *,
        idle_timeout_seconds: float = DEFAULT_BROWSER_IDLE_TIMEOUT_SECONDS,
        close_grace_seconds: float = DEFAULT_BROWSER_CLOSE_GRACE_SECONDS,
        startup_timeout_seconds: float = DEFAULT_BROWSER_STARTUP_TIMEOUT_SECONDS,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.idle_timeout_seconds = idle_timeout_seconds
        self.close_grace_seconds = close_grace_seconds
        self.startup_timeout_seconds = startup_timeout_seconds
        self._now = now or time.monotonic
        self._lock = threading.Lock()
        self._last_seen_at: float | None = None
        self._closing_requested_at: float | None = None
        self._startup_deadline = self._now() + max(startup_timeout_seconds, 1.0)

    def record_heartbeat(self) -> None:
        """Record that a browser page for this launcher instance is still open."""

        with self._lock:
            self._last_seen_at = self._now()
            self._closing_requested_at = None

    def record_page_closing(self) -> None:
        """Record that a browser page is navigating away or closing."""

        with self._lock:
            self._closing_requested_at = self._now()

    def should_shutdown(self) -> bool:
        """Return True when the launcher should stop the local server."""

        now = self._now()
        with self._lock:
            if self._closing_requested_at is not None:
                if self._last_seen_at is None or self._last_seen_at <= self._closing_requested_at:
                    return now - self._closing_requested_at >= self.close_grace_seconds
            if self._last_seen_at is None:
                return now >= self._startup_deadline
            return now - self._last_seen_at >= self.idle_timeout_seconds


@dataclass(slots=True)
class OperatorLauncherConfig:
    """Runtime settings for the local operator launcher."""

    host: str = "127.0.0.1"
    port: int = 5000
    open_browser: bool = True
    wait_timeout_seconds: float = DEFAULT_WAIT_TIMEOUT_SECONDS
    ready_file: str | None = None
    shutdown_on_browser_close: bool = False


class LauncherDependencyError(RuntimeError):
    """Raised when the local operator interface dependencies are unavailable."""


def build_parser() -> argparse.ArgumentParser:
    """Build the operator launcher parser."""

    parser = argparse.ArgumentParser(
        prog="occams-beard-operator",
        description="Start the local operator interface and open it in a browser.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=5000, help="Local TCP port to listen on.")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Start the local server without opening a browser tab.",
    )
    parser.add_argument(
        "--wait-timeout",
        type=float,
        default=DEFAULT_WAIT_TIMEOUT_SECONDS,
        help="Seconds to wait for the local server to accept connections before failing.",
    )
    parser.add_argument(
        "--ready-file",
        help="Write the bound local URL to PATH after the server is ready.",
    )
    parser.add_argument(
        "--shutdown-on-browser-close",
        action="store_true",
        help="Stop the local server after the last browser page is closed.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable INFO-level logging.")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG-level logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the operator launcher."""

    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(verbose=args.verbose, debug=args.debug)
    return launch_operator_interface(
        OperatorLauncherConfig(
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
            wait_timeout_seconds=args.wait_timeout,
            ready_file=args.ready_file,
            shutdown_on_browser_close=args.shutdown_on_browser_close,
        )
    )


def launch_operator_interface(config: OperatorLauncherConfig) -> int:
    """Start the local web server and optionally open a browser."""

    try:
        create_app, make_server = _load_web_dependencies()
    except LauncherDependencyError as exc:
        LOGGER.error("%s", exc)
        return 1

    presence_tracker = (
        BrowserPresenceTracker() if config.shutdown_on_browser_close else None
    )
    app = create_app(_browser_presence_app_config(presence_tracker))

    try:
        server = _make_server_with_fallback(make_server, config.host, config.port, app)
    except OSError as exc:
        LOGGER.error(
            "Operator interface failed to bind: host=%s port=%s error=%s",
            config.host,
            config.port,
            exc,
        )
        return 1

    bind_port = int(server.server_port)
    browser_url = _build_browser_url(config.host, bind_port)

    server_thread = threading.Thread(
        target=server.serve_forever,
        name="occams-beard-operator-server",
        daemon=True,
    )
    server_thread.start()

    if not _wait_for_server(browser_url, timeout_seconds=config.wait_timeout_seconds):
        LOGGER.error(
            "Operator interface did not become ready in time: url=%s timeout_seconds=%.1f",
            browser_url,
            config.wait_timeout_seconds,
        )
        server.shutdown()
        server_thread.join(timeout=5)
        return 1

    LOGGER.info("Operator interface ready: url=%s", browser_url)
    _write_ready_file(config.ready_file, browser_url)
    if config.open_browser:
        _open_browser(browser_url)

    print(f"Occam's Beard operator interface is running at {browser_url}")
    if config.shutdown_on_browser_close:
        print("The local server will stop after the last browser page is closed.")
    else:
        print("Press Ctrl-C to stop the local server.")

    try:
        while server_thread.is_alive():
            if presence_tracker is not None and presence_tracker.should_shutdown():
                LOGGER.info(
                    "Stopping operator interface after the launcher browser page closed or "
                    "stopped checking in: url=%s",
                    browser_url,
                )
                break
            server_thread.join(timeout=0.5)
    except KeyboardInterrupt:
        LOGGER.info("Stopping operator interface: url=%s", browser_url)
    finally:
        server.shutdown()
        server_thread.join(timeout=5)

    return 0


def _load_web_dependencies():
    """Load Flask app and WSGI server dependencies only when needed."""

    try:
        app_module = importlib.import_module("occams_beard.app")
        serving_module = importlib.import_module("werkzeug.serving")
    except ModuleNotFoundError as exc:
        raise LauncherDependencyError(
            "Operator interface dependencies are missing. "
            "Install the project with `pip install -e .` or use the macOS "
            "`Open Device Check.command` launcher in the repo root so it can bootstrap a "
            "local `.venv`."
        ) from exc

    return app_module.create_app, serving_module.make_server


def _build_browser_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host == "0.0.0.0" else host
    return f"http://{browser_host}:{port}"


def _make_server_with_fallback(make_server, host: str, preferred_port: int, app):
    """Create a local server, retrying on an ephemeral port if the preferred one is busy."""

    try:
        return make_server(host, preferred_port, app)
    except OSError as exc:
        if not _is_address_in_use_error(exc):
            raise

        LOGGER.warning(
            "Requested operator port is unavailable; selecting an ephemeral fallback port instead: "
            "host=%s requested_port=%s",
            host,
            preferred_port,
        )
        return make_server(host, 0, app)


def _is_address_in_use_error(exc: OSError) -> bool:
    """Return True when the bind failure corresponds to an occupied local port."""

    error_text = str(exc).lower()
    return exc.errno == 48 or "address already in use" in error_text


def _wait_for_server(url: str, timeout_seconds: float) -> bool:
    host, port = _parse_url_target(url)
    deadline = time.monotonic() + max(timeout_seconds, 0.1)
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _parse_url_target(url: str) -> tuple[str, int]:
    _, _, host_port = url.partition("://")
    host, _, port_text = host_port.partition(":")
    return host, int(port_text)


def _open_browser(url: str) -> None:
    try:
        opened = webbrowser.open(url, new=2)
    except webbrowser.Error as exc:
        LOGGER.warning("Browser launch failed: url=%s error=%s", url, exc)
        return

    if not opened:
        LOGGER.warning("Browser launch was not accepted by the desktop environment: url=%s", url)


def _write_ready_file(path: str | None, url: str) -> None:
    """Persist the ready URL for parent launchers that need an exact browser target."""

    if not path:
        return

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(url)
        handle.write("\n")


def _browser_presence_app_config(
    tracker: BrowserPresenceTracker | None,
) -> dict[str, object]:
    if tracker is None:
        return {}
    return {
        "LAUNCHER_BROWSER_PRESENCE_TRACKER": tracker,
        "LAUNCHER_BROWSER_PRESENCE_INTERVAL_MS": int(
            DEFAULT_BROWSER_HEARTBEAT_INTERVAL_SECONDS * 1000
        ),
    }


def _configure_logging(verbose: bool, debug: bool) -> None:
    level = logging.WARNING
    if verbose:
        level = logging.INFO
    if debug:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


if __name__ == "__main__":
    raise SystemExit(main())
