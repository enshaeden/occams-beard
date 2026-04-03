"""Local Flask app for running and reviewing endpoint diagnostics."""

from __future__ import annotations

import argparse
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from uuid import uuid4

from flask import Flask, Response, abort, current_app, redirect, render_template, request, url_for

from endpoint_diagnostics_lab.defaults import DEFAULT_CHECKS, DEFAULT_DNS_HOSTS, DEFAULT_TCP_TARGETS
from endpoint_diagnostics_lab.models import EndpointDiagnosticResult, TcpTarget
from endpoint_diagnostics_lab.runner import DiagnosticsRunOptions, build_run_options, run_diagnostics
from endpoint_diagnostics_lab.serializers import to_json_text


@dataclass(slots=True)
class RunRecord:
    """In-memory record of a completed diagnostics run."""

    run_id: str
    options: DiagnosticsRunOptions
    result: EndpointDiagnosticResult
    json_text: str


class RecentRunsStore:
    """Small in-memory store for recent local diagnostics results."""

    def __init__(self, max_entries: int = 10) -> None:
        self._max_entries = max_entries
        self._records: OrderedDict[str, RunRecord] = OrderedDict()
        self._lock = Lock()

    def save(self, record: RunRecord) -> None:
        with self._lock:
            self._records[record.run_id] = record
            self._records.move_to_end(record.run_id)
            while len(self._records) > self._max_entries:
                self._records.popitem(last=False)

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            record = self._records.get(run_id)
            if record is None:
                return None
            self._records.move_to_end(run_id)
            return record


def create_app(config: dict | None = None) -> Flask:
    """Create the local diagnostics Flask app."""

    app = Flask(__name__)
    app.config.update(
        RUN_OPTIONS_FACTORY=build_run_options,
        RUN_EXECUTOR=run_diagnostics,
        RUN_RESULTS_STORE=RecentRunsStore(),
    )
    if config:
        app.config.update(config)

    app.add_template_filter(_format_bytes, "format_bytes")
    app.add_template_filter(_format_percent, "format_percent")
    app.add_template_filter(_format_latency, "format_latency")
    app.add_template_filter(_join_addresses, "join_addresses")
    app.add_template_filter(_yes_no, "yes_no")

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            checks_catalog=DEFAULT_CHECKS,
            form_state=_query_form_state(),
            page_title="Run Diagnostics",
        )

    @app.post("/run")
    def run():
        form_state = _form_state_from_request()
        try:
            options = current_app.config["RUN_OPTIONS_FACTORY"](
                checks=form_state["checks_csv"],
                targets=form_state["targets"],
                dns_hosts=form_state["dns_hosts"],
                enable_ping=form_state["enable_ping"],
                enable_trace=form_state["enable_trace"],
            )
            result = current_app.config["RUN_EXECUTOR"](options)
        except ValueError as exc:
            form_state["error"] = str(exc)
            return (
                render_template(
                    "index.html",
                    checks_catalog=DEFAULT_CHECKS,
                    form_state=form_state,
                    page_title="Run Diagnostics",
                ),
                400,
            )

        run_id = uuid4().hex
        record = RunRecord(
            run_id=run_id,
            options=options,
            result=result,
            json_text=to_json_text(result),
        )
        current_app.config["RUN_RESULTS_STORE"].save(record)
        return redirect(url_for("results", run_id=run_id))

    @app.get("/results/<run_id>")
    def results(run_id: str):
        record = _get_record_or_404(run_id)
        return render_template(
            "results.html",
            page_title="Diagnostics Results",
            record=record,
            result=record.result,
            selected_checks=set(record.result.metadata.selected_checks),
            rerun_url=_rerun_url(record.options),
        )

    @app.get("/results/<run_id>/result.json")
    def download_json(run_id: str):
        record = _get_record_or_404(run_id)
        return Response(
            record.json_text + "\n",
            mimetype="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=occams-beard-{run_id}.json"
            },
        )

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


def _get_record_or_404(run_id: str) -> RunRecord:
    record = current_app.config["RUN_RESULTS_STORE"].get(run_id)
    if record is None:
        abort(404)
    return record


def _query_form_state() -> dict[str, object]:
    checks_csv = request.args.get("checks")
    selected_checks = (
        checks_csv.split(",")
        if checks_csv
        else list(DEFAULT_CHECKS)
    )
    targets_text = request.args.get("targets")
    dns_hosts_text = request.args.get("dns_hosts")
    return {
        "selected_checks": selected_checks,
        "checks_csv": checks_csv,
        "targets_text": targets_text if targets_text is not None else _targets_text(DEFAULT_TCP_TARGETS),
        "dns_hosts_text": dns_hosts_text if dns_hosts_text is not None else "\n".join(DEFAULT_DNS_HOSTS),
        "enable_ping": request.args.get("enable_ping") == "1",
        "enable_trace": request.args.get("enable_trace") == "1",
        "error": None,
    }


def _form_state_from_request() -> dict[str, object]:
    selected_checks = request.form.getlist("checks")
    targets = _split_multiline_entries(request.form.get("targets"))
    dns_hosts = _split_multiline_entries(request.form.get("dns_hosts"))
    return {
        "selected_checks": selected_checks or list(DEFAULT_CHECKS),
        "checks_csv": ",".join(selected_checks) or None,
        "targets": targets,
        "dns_hosts": dns_hosts,
        "targets_text": request.form.get("targets", ""),
        "dns_hosts_text": request.form.get("dns_hosts", ""),
        "enable_ping": request.form.get("enable_ping") == "on",
        "enable_trace": request.form.get("enable_trace") == "on",
        "error": None,
    }


def _rerun_url(options: DiagnosticsRunOptions) -> str:
    return url_for(
        "index",
        checks=",".join(options.selected_checks),
        targets=_targets_text(options.targets),
        dns_hosts="\n".join(options.dns_hosts),
        enable_ping="1" if options.enable_ping else "0",
        enable_trace="1" if options.enable_trace else "0",
    )


def _split_multiline_entries(raw_text: str | None) -> list[str]:
    if not raw_text:
        return []
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


def _targets_text(targets: tuple[TcpTarget, ...] | list[TcpTarget]) -> str:
    lines = []
    for target in targets:
        lines.append(f"{target.host}:{target.port}")
    return "\n".join(lines)


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    suffixes = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    for suffix in suffixes:
        if size < 1024 or suffix == suffixes[-1]:
            return f"{size:.1f} {suffix}"
        size /= 1024
    return f"{value} B"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f}%"


def _format_latency(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f} ms"


def _join_addresses(values: list[str]) -> str:
    return ", ".join(values) if values else "none detected"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
