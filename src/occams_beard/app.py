"""Local Flask app entry point for the troubleshooting interface."""

from __future__ import annotations

import argparse
from copy import deepcopy

from flask import Flask, current_app, request, url_for

from occams_beard.runner import build_run_options, run_diagnostics
from occams_beard.runtime_identity import current_runtime_metadata
from occams_beard.web.filters import register_template_filters
from occams_beard.web.routes import register_web_routes
from occams_beard.web.sessions import RecentRunsStore


def create_app(config: dict | None = None) -> Flask:
    """Create the local troubleshooting Flask app."""

    app = Flask(__name__)
    app.config.update(
        RUN_OPTIONS_FACTORY=build_run_options,
        RUN_EXECUTOR=run_diagnostics,
        RUN_RESULTS_STORE=RecentRunsStore(),
        LAUNCHER_BROWSER_PRESENCE_TRACKER=None,
        LAUNCHER_BROWSER_PRESENCE_INTERVAL_MS=15000,
        RUNTIME_METADATA=current_runtime_metadata(),
    )
    if config:
        app.config.update(config)

    register_template_filters(app)
    register_web_routes(app)

    @app.context_processor
    def inject_launcher_browser_presence() -> dict[str, object]:
        tracker = current_app.config.get("LAUNCHER_BROWSER_PRESENCE_TRACKER")
        browser_presence = None
        if tracker is not None:
            browser_presence = {
                "heartbeat_url": url_for("launcher_browser_presence"),
                "closing_url": url_for("launcher_browser_closing"),
                "interval_ms": int(current_app.config["LAUNCHER_BROWSER_PRESENCE_INTERVAL_MS"]),
            }
        runtime_metadata = deepcopy(current_app.config["RUNTIME_METADATA"])
        runtime_metadata["server_origin"] = request.host_url.rstrip("/")
        return {"browser_presence": browser_presence, "runtime_metadata": runtime_metadata}

    return app


def main(argv: list[str] | None = None) -> int:
    """Run the local Flask app."""

    parser = argparse.ArgumentParser(
        prog="occams-beard-web",
        description="Run the local Occam's Beard web interface.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=5000, help="Local TCP port to listen on.")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode.")
    args = parser.parse_args(argv)

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
