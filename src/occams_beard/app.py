"""Local Flask app for running and reviewing host and network diagnostics."""

from __future__ import annotations

import argparse
import inspect
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock, Thread
from typing import Any, Literal, cast
from uuid import uuid4

from flask import (
    Flask,
    Response,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from occams_beard.defaults import DEFAULT_CHECKS, DEFAULT_DNS_HOSTS, DEFAULT_TCP_TARGETS
from occams_beard.execution import (
    DOMAIN_LABELS,
    next_execution_step_label,
    planned_execution_step_breakdown,
    planned_execution_step_count,
)
from occams_beard.models import (
    DiagnosticProfile,
    DomainExecution,
    EndpointDiagnosticResult,
    RedactionLevel,
    TcpTarget,
)
from occams_beard.profile_catalog import ProfileCatalogIssue, get_profile, get_profile_catalog
from occams_beard.runner import DiagnosticsRunOptions, build_run_options, run_diagnostics
from occams_beard.serializers import to_json_text
from occams_beard.support_bundle import support_bundle_response_body
from occams_beard.web_presenter import (
    SELF_SERVE_MODE,
    SUPPORT_MODE,
    build_collection_plan,
    build_results_view,
    get_mode_option,
    get_symptom_option,
    list_mode_options,
    list_symptom_options,
    normalize_mode,
    resolve_self_serve_profile_id,
    suggest_support_profile_id,
)

RunStatus = Literal["queued", "running", "completed", "failed"]


@dataclass(slots=True)
class RunExperience:
    """Presentation context for a local diagnostics run."""

    mode: str
    mode_label: str
    symptom_id: str | None = None
    symptom_label: str | None = None
    previous_run_id: str | None = None


@dataclass(slots=True)
class RunSession:
    """In-memory record for a local diagnostics run and its progress state."""

    run_id: str
    options: DiagnosticsRunOptions
    experience: RunExperience
    status: RunStatus = "queued"
    progress_execution: list[DomainExecution] = field(default_factory=list)
    current_domain: str | None = None
    completed_count: int = 0
    total_count: int = 0
    completed_steps_by_domain: dict[str, int] = field(default_factory=dict)
    result: EndpointDiagnosticResult | None = None
    json_text: str | None = None
    error: str | None = None


class RecentRunsStore:
    """Small in-memory store for recent local diagnostics sessions."""

    def __init__(self, max_entries: int = 10) -> None:
        self._max_entries = max_entries
        self._records: OrderedDict[str, RunSession] = OrderedDict()
        self._lock = Lock()

    def create(self, session: RunSession) -> None:
        with self._lock:
            self._records[session.run_id] = session
            self._records.move_to_end(session.run_id)
            while len(self._records) > self._max_entries:
                self._records.popitem(last=False)

    def get(self, run_id: str) -> RunSession | None:
        with self._lock:
            session = self._records.get(run_id)
            if session is None:
                return None
            self._records.move_to_end(run_id)
            return session

    def get_completed(self, run_id: str) -> RunSession | None:
        with self._lock:
            session = self._records.get(run_id)
            if session is None or session.status != "completed":
                return None
            self._records.move_to_end(run_id)
            return session

    def update_progress(
        self,
        run_id: str,
        *,
        progress_execution: list[DomainExecution],
        current_domain: str | None,
        completed_count: int,
        total_count: int,
        completed_steps_by_domain: dict[str, int],
    ) -> None:
        with self._lock:
            session = self._records.get(run_id)
            if session is None:
                return
            session.status = "running"
            session.progress_execution = progress_execution
            session.current_domain = current_domain
            session.completed_count = completed_count
            session.total_count = total_count
            session.completed_steps_by_domain = completed_steps_by_domain
            self._records.move_to_end(run_id)

    def complete(
        self,
        run_id: str,
        *,
        result: EndpointDiagnosticResult,
        json_text: str,
    ) -> None:
        with self._lock:
            session = self._records.get(run_id)
            if session is None:
                return
            session.status = "completed"
            session.result = result
            session.json_text = json_text
            session.progress_execution = result.execution
            session.current_domain = None
            session.completed_count = planned_execution_step_count(session.options)
            session.total_count = planned_execution_step_count(session.options)
            session.completed_steps_by_domain = planned_execution_step_breakdown(session.options)
            session.error = None
            self._records.move_to_end(run_id)

    def fail(self, run_id: str, error: str) -> None:
        with self._lock:
            session = self._records.get(run_id)
            if session is None:
                return
            session.status = "failed"
            session.current_domain = None
            session.error = error
            self._records.move_to_end(run_id)


def create_app(config: dict | None = None) -> Flask:
    """Create the local diagnostics Flask app."""

    app = Flask(__name__)
    app.config.update(
        RUN_OPTIONS_FACTORY=build_run_options,
        RUN_EXECUTOR=run_diagnostics,
        RUN_RESULTS_STORE=RecentRunsStore(),
        LAUNCHER_BROWSER_PRESENCE_TRACKER=None,
        LAUNCHER_BROWSER_PRESENCE_INTERVAL_MS=15000,
    )
    if config:
        app.config.update(config)

    app.add_template_filter(_format_bytes, "format_bytes")
    app.add_template_filter(_format_percent, "format_percent")
    app.add_template_filter(_format_latency, "format_latency")
    app.add_template_filter(_join_addresses, "join_addresses")
    app.add_template_filter(_yes_no, "yes_no")

    @app.context_processor
    def inject_launcher_browser_presence() -> dict[str, object]:
        tracker = current_app.config.get("LAUNCHER_BROWSER_PRESENCE_TRACKER")
        if tracker is None:
            return {"browser_presence": None}
        return {
            "browser_presence": {
                "heartbeat_url": url_for("launcher_browser_presence"),
                "closing_url": url_for("launcher_browser_closing"),
                "interval_ms": int(current_app.config["LAUNCHER_BROWSER_PRESENCE_INTERVAL_MS"]),
            }
        }

    @app.get("/")
    def index():
        try:
            form_state = _query_form_state()
        except ValueError as exc:
            form_state = _default_form_state()
            form_state["error"] = str(exc)
        profiles, profile_catalog_issues = _profile_catalog_context()
        return render_template(
            "index.html",
            mode_options=list_mode_options(),
            symptom_options=list_symptom_options(),
            profiles=profiles,
            profile_catalog_issues=profile_catalog_issues,
            form_state=form_state,
            page_title=_page_title(cast(str | None, form_state["mode"])),
        )

    @app.get("/self-serve/plan")
    def self_serve_plan():
        try:
            form_state = _query_form_state()
        except ValueError as exc:
            abort(400, description=str(exc))
        if form_state["mode"] != SELF_SERVE_MODE:
            abort(400, description="Self-serve plan requests must use self-serve mode.")
        return render_template(
            "_self_serve_plan.html",
            form_state=form_state,
        )

    @app.post("/__launcher_presence")
    def launcher_browser_presence():
        tracker = current_app.config.get("LAUNCHER_BROWSER_PRESENCE_TRACKER")
        if tracker is None:
            abort(404)
        tracker.record_heartbeat()
        return ("", 204)

    @app.post("/__launcher_presence/closing")
    def launcher_browser_closing():
        tracker = current_app.config.get("LAUNCHER_BROWSER_PRESENCE_TRACKER")
        if tracker is None:
            abort(404)
        tracker.record_page_closing()
        return ("", 204)

    @app.post("/run")
    def run():
        try:
            form_state = _form_state_from_request()
        except ValueError as exc:
            form_state = _request_error_form_state(str(exc))
            profiles, profile_catalog_issues = _profile_catalog_context()
            return (
                render_template(
                    "index.html",
                    mode_options=list_mode_options(),
                    symptom_options=list_symptom_options(),
                    profiles=profiles,
                    profile_catalog_issues=profile_catalog_issues,
                    form_state=form_state,
                    page_title=_page_title(cast(str | None, form_state["mode"])),
                ),
                400,
            )

        try:
            options = current_app.config["RUN_OPTIONS_FACTORY"](
                checks=form_state["checks_csv"],
                targets=form_state["targets"],
                dns_hosts=form_state["dns_hosts"],
                profile_id=form_state["profile_id"],
                enable_ping=form_state["enable_ping"],
                enable_trace=form_state["enable_trace"],
                capture_raw_commands=form_state["capture_raw_commands"],
            )
        except ValueError as exc:
            form_state["error"] = str(exc)
            profiles, profile_catalog_issues = _profile_catalog_context()
            return (
                render_template(
                    "index.html",
                    mode_options=list_mode_options(),
                    symptom_options=list_symptom_options(),
                    profiles=profiles,
                    profile_catalog_issues=profile_catalog_issues,
                    form_state=form_state,
                    page_title=_page_title(cast(str | None, form_state["mode"])),
                ),
                400,
            )

        run_id = uuid4().hex
        mode_option = cast(dict[str, str], form_state["mode_option"])
        selected_symptom = cast(dict[str, str] | None, form_state["selected_symptom"])
        experience = RunExperience(
            mode=cast(str, form_state["mode"]),
            mode_label=mode_option["label"],
            symptom_id=cast(str | None, form_state["symptom_id"]),
            symptom_label=(
                selected_symptom["label"] if selected_symptom is not None else None
            ),
            previous_run_id=cast(str | None, form_state["from_run_id"]),
        )
        session = RunSession(
            run_id=run_id,
            options=options,
            experience=experience,
            progress_execution=_initial_progress_execution(options),
            current_domain="host",
            completed_count=0,
            total_count=planned_execution_step_count(options),
            completed_steps_by_domain={},
        )
        current_app.config["RUN_RESULTS_STORE"].create(session)
        app_object = current_app._get_current_object()  # type: ignore[attr-defined]
        _start_run_thread(cast(Flask, app_object), run_id)
        return redirect(url_for("run_progress", run_id=run_id))

    @app.get("/runs/<run_id>")
    def run_progress(run_id: str):
        session = _get_session_or_404(run_id)
        if session.status == "completed":
            return redirect(url_for("results", run_id=run_id))
        return render_template(
            "run_progress.html",
            page_title=f"{session.experience.mode_label} Progress",
            session=session,
            view=_build_progress_view(session),
            rerun_url=_rerun_url(session),
        )

    @app.get("/runs/<run_id>/status")
    def run_status(run_id: str):
        session = _get_session_or_404(run_id)
        payload = _build_progress_view(session)
        payload["results_url"] = url_for("results", run_id=run_id)
        payload["rerun_url"] = _rerun_url(session)
        return jsonify(payload)

    @app.get("/results/<run_id>")
    def results(run_id: str):
        session = _get_session_or_404(run_id)
        if session.status != "completed" or session.result is None:
            return redirect(url_for("run_progress", run_id=run_id))
        previous_results_url = (
            url_for("results", run_id=session.experience.previous_run_id)
            if session.experience.previous_run_id
            and current_app.config["RUN_RESULTS_STORE"].get_completed(
                session.experience.previous_run_id
            )
            else None
        )
        continue_with_support_url = None
        if session.experience.mode == SELF_SERVE_MODE:
            continue_with_support_url = _support_bridge_url(session)
        view = build_results_view(
            result=session.result,
            options=session.options,
            mode=session.experience.mode,
            continue_with_support_url=continue_with_support_url,
            previous_results_url=previous_results_url,
        )
        return render_template(
            "results.html",
            page_title=f"{session.experience.mode_label} Results",
            record=session,
            result=session.result,
            rerun_url=_rerun_url(session),
            view=view,
        )

    @app.get("/results/<run_id>/result.json")
    def download_json(run_id: str):
        record = _get_completed_record_or_409(run_id)
        return Response(
            cast(str, record.json_text) + "\n",
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename=occams-beard-{run_id}.json"},
        )

    @app.get("/results/<run_id>/support-bundle.zip")
    def download_support_bundle(run_id: str):
        record = _get_completed_record_or_409(run_id)
        redaction_level = _resolve_redaction_level(request.args.get("redaction_level"))
        include_raw_command_capture = request.args.get("include_raw") == "1"
        body = support_bundle_response_body(
            cast(EndpointDiagnosticResult, record.result),
            redaction_level=redaction_level,
            include_raw_command_capture=include_raw_command_capture,
        )
        return Response(
            body,
            mimetype="application/zip",
            headers={
                "Content-Disposition": (
                    f"attachment; filename=occams-beard-{run_id}-support-bundle.zip"
                )
            },
        )

    return app


def _start_run_thread(app: Flask, run_id: str) -> None:
    worker = Thread(
        target=_run_session,
        args=(app, run_id),
        daemon=True,
        name=f"occams-beard-run-{run_id[:8]}",
    )
    worker.start()


def _run_session(app: Flask, run_id: str) -> None:
    with app.app_context():
        session = _get_store().get(run_id)
        if session is None:
            return

        def progress_callback(
            progress_execution: list[DomainExecution],
            active_domain: str | None,
            completed_count: int,
            total_count: int,
            completed_steps_by_domain: dict[str, int],
        ) -> None:
            _get_store().update_progress(
                run_id,
                progress_execution=progress_execution,
                current_domain=active_domain,
                completed_count=completed_count,
                total_count=total_count,
                completed_steps_by_domain=completed_steps_by_domain,
            )

        try:
            result = _execute_with_optional_progress(
                current_app.config["RUN_EXECUTOR"],
                session.options,
                progress_callback=progress_callback,
            )
        except ValueError as exc:
            _get_store().fail(run_id, str(exc))
            return
        except Exception:
            current_app.logger.exception("Diagnostics run %s failed", run_id)
            _get_store().fail(
                run_id,
                (
                    "The run stopped before results were ready. "
                    "Try again or continue with support if the issue keeps happening."
                ),
            )
            return

        _get_store().complete(
            run_id,
            result=result,
            json_text=to_json_text(result),
        )


def _execute_with_optional_progress(
    executor: Any,
    options: DiagnosticsRunOptions,
    *,
    progress_callback: Any,
) -> EndpointDiagnosticResult:
    try:
        signature = inspect.signature(executor)
    except (TypeError, ValueError):
        return executor(options)

    accepts_progress = "progress_callback" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    if accepts_progress:
        return executor(options, progress_callback=progress_callback)
    return executor(options)


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


def _page_title(mode: str | None) -> str:
    if mode == SELF_SERVE_MODE:
        return "Check My Device"
    if mode == SUPPORT_MODE:
        return "Work With Support"
    return "Choose a Check Path"


def _initial_progress_execution(options: DiagnosticsRunOptions) -> list[DomainExecution]:
    selected_domains = set(options.selected_checks) | {"host"}
    progress_execution: list[DomainExecution] = []
    for domain in DEFAULT_CHECKS:
        selected = domain in selected_domains
        progress_execution.append(
            DomainExecution(
                domain=domain,
                label=DOMAIN_LABELS[domain],
                status="not_run",
                selected=selected,
                summary=(
                    "This domain is currently running."
                    if domain == "host"
                    else (
                        "This domain is queued for the run."
                        if selected
                        else "Optional and not selected for this run."
                    )
                ),
                creates_network_egress=domain in {"dns", "connectivity", "services"},
            )
        )
    return progress_execution


def _get_store() -> RecentRunsStore:
    return cast(RecentRunsStore, current_app.config["RUN_RESULTS_STORE"])


def _get_session_or_404(run_id: str) -> RunSession:
    session = _get_store().get(run_id)
    if session is None:
        abort(404)
    return session


def _get_completed_record_or_409(run_id: str) -> RunSession:
    session = _get_session_or_404(run_id)
    if session.status != "completed" or session.result is None or session.json_text is None:
        abort(409, description="This run is not complete yet.")
    return session


def _build_progress_view(session: RunSession) -> dict[str, object]:
    total_count = session.total_count or planned_execution_step_count(session.options)
    completed_count = min(session.completed_count, total_count)
    progress_percent = int((completed_count / total_count) * 100) if total_count else 0
    current_domain_label = (
        DOMAIN_LABELS.get(session.current_domain, session.current_domain.replace("-", " ").title())
        if session.current_domain
        else None
    )
    current_substep_label = (
        next_execution_step_label(
            session.options,
            session.current_domain,
            session.completed_steps_by_domain.get(session.current_domain, 0),
        )
        if session.current_domain is not None
        else None
    )
    if session.status == "failed":
        status_tone = "attention"
        status_label = "Run stopped"
        headline = "The local run stopped before results were ready."
        body = session.error or "Try again or continue with support."
    elif session.status == "completed":
        status_tone = "clear"
        status_label = "Results ready"
        headline = "The run is complete."
        body = "Opening the local results view."
    else:
        status_tone = "running"
        status_label = "Running locally"
        headline = (
            "Checking your device with the selected plan."
            if session.experience.mode == SELF_SERVE_MODE
            else "Following the support-guided plan on this device."
        )
        body = (
            (
                f"Currently running: {current_domain_label}. {current_substep_label}."
                if current_domain_label is not None and current_substep_label is not None
                else (
                    f"Currently running: {current_domain_label}."
                    if current_domain_label is not None
                    else "Preparing the next step."
                )
            )
        )

    update_notice = "This page updates automatically."
    presence_notice = "You can stay here or come back when the run finishes."
    mode_notice = (
        "You do not need to refresh this page while the local check runs."
        if session.experience.mode == SELF_SERVE_MODE
        else "Support-guided runs can take longer when they include deeper checks or extra probes."
    )

    rows = []
    step_breakdown = planned_execution_step_breakdown(session.options)
    for record in session.progress_execution:
        total_steps = step_breakdown.get(record.domain, 0)
        completed_steps = session.completed_steps_by_domain.get(record.domain, 0)
        if not record.selected:
            row_status = "not_run"
            row_status_label = "Optional"
            duration_label = "Not selected"
            summary = "Optional and not selected for this run."
        elif session.status in {"queued", "running"} and record.domain == session.current_domain:
            row_status = "running"
            row_status_label = "Running now"
            duration_label = "Running"
            summary = (
                f"{current_substep_label}."
                if current_substep_label is not None
                else record.summary or "This check area is running now."
            )
        elif session.status in {"queued", "running"} and record.status == "not_run":
            row_status = "not_run"
            row_status_label = "Queued"
            duration_label = "Queued"
            summary = "Queued and waiting to run."
        else:
            row_status = _progress_row_tone(record.status)
            row_status_label = "Completed"
            duration_label = (
                f"{record.duration_ms} ms" if record.duration_ms is not None else "Completed"
            )
            summary = _progress_row_summary(record)
        rows.append(
            {
                "label": record.label,
                "summary": summary,
                "status": row_status,
                "status_label": row_status_label,
                "step_progress_label": (
                    f"{completed_steps}/{total_steps}" if record.selected and total_steps else "Optional"
                ),
                "duration_label": duration_label,
                "scope_label": (
                    "Creates network traffic" if record.creates_network_egress else "Local only"
                ),
                "subdued": bool(
                    session.status in {"queued", "running"}
                    and record.selected
                    and record.status == "passed"
                ),
            }
        )

    return {
        "run_id": session.run_id,
        "mode_label": session.experience.mode_label,
        "status": session.status,
        "status_tone": status_tone,
        "status_label": status_label,
        "headline": headline,
        "body": body,
        "error": session.error,
        "completed_count": completed_count,
        "total_count": total_count,
        "progress_percent": progress_percent,
        "progress_text": f"{completed_count} of {total_count} planned probe steps complete.",
        "current_domain_label": current_domain_label,
        "current_substep_label": current_substep_label,
        "update_notice": update_notice,
        "presence_notice": presence_notice,
        "mode_notice": mode_notice,
        "rows": rows,
    }


def _query_form_state() -> dict[str, object]:
    mode = normalize_mode(request.args.get("mode"))
    if mode is None:
        return _default_form_state()

    source_record = _query_previous_record()
    mode_option = get_mode_option(mode)
    if mode_option is None:
        raise ValueError("Unknown experience path.")

    if mode == SELF_SERVE_MODE:
        symptom = get_symptom_option(request.args.get("symptom"))
        profile = _self_serve_profile(symptom["id"] if symptom else None)
    else:
        symptom = None
        profile = get_profile(
            request.args.get("profile") or _default_support_profile_id(source_record)
        )

    checks_csv = request.args.get("checks")
    selected_checks = (
        [item for item in checks_csv.split(",") if item]
        if checks_csv
        else list(profile.recommended_checks if profile is not None else [])
    )
    targets_text = request.args.get("targets")
    dns_hosts_text = request.args.get("dns_hosts")
    effective_targets = (
        _split_multiline_entries(targets_text)
        if targets_text is not None
        else _default_target_lines(profile)
    )
    effective_dns_hosts = (
        _split_multiline_entries(dns_hosts_text)
        if dns_hosts_text is not None
        else _default_dns_lines(profile)
    )

    return _build_form_state(
        mode=mode,
        mode_option=mode_option,
        selected_symptom=symptom,
        selected_profile=profile,
        selected_checks=selected_checks,
        targets_text=targets_text if targets_text is not None else "\n".join(effective_targets),
        dns_hosts_text=(
            dns_hosts_text if dns_hosts_text is not None else "\n".join(effective_dns_hosts)
        ),
        enable_ping=request.args.get("enable_ping") == "1",
        enable_trace=request.args.get("enable_trace") == "1",
        capture_raw_commands=request.args.get("capture_raw_commands") == "1",
        from_run_id=source_record.run_id if source_record is not None else None,
        bridge=_bridge_context(source_record, profile.profile_id if profile else None),
        error_message=None,
    )


def _form_state_from_request(*, error_message: str | None = None) -> dict[str, object]:
    mode = normalize_mode(request.form.get("mode"))
    if mode is None:
        raise ValueError("Choose how you want to start before running diagnostics.")

    mode_option = get_mode_option(mode)
    if mode_option is None:
        raise ValueError("Unknown experience path.")

    source_record = _optional_record(request.form.get("from_run_id"))

    if mode == SELF_SERVE_MODE:
        symptom = get_symptom_option(request.form.get("symptom_id"))
        if symptom is None:
            raise ValueError("Choose the option that best matches the problem first.")
        profile = _self_serve_profile(symptom["id"])
    else:
        symptom = None
        profile = get_profile(request.form.get("profile_id") or "custom-profile")

    selected_checks = request.form.getlist("checks")
    targets_text = request.form.get("targets")
    dns_hosts_text = request.form.get("dns_hosts")
    effective_targets = (
        _split_multiline_entries(targets_text) if targets_text else _default_target_lines(profile)
    )
    effective_dns_hosts = (
        _split_multiline_entries(dns_hosts_text)
        if dns_hosts_text
        else _default_dns_lines(profile)
    )
    effective_checks = selected_checks or list(profile.recommended_checks if profile else [])

    return _build_form_state(
        mode=mode,
        mode_option=mode_option,
        selected_symptom=symptom,
        selected_profile=profile,
        selected_checks=effective_checks,
        targets_text=targets_text or "\n".join(effective_targets),
        dns_hosts_text=dns_hosts_text or "\n".join(effective_dns_hosts),
        enable_ping=request.form.get("enable_ping") == "on",
        enable_trace=request.form.get("enable_trace") == "on",
        capture_raw_commands=request.form.get("capture_raw_commands") == "on",
        from_run_id=source_record.run_id if source_record is not None else None,
        bridge=_bridge_context(source_record, profile.profile_id if profile else None),
        error_message=error_message,
    )


def _request_error_form_state(error_message: str) -> dict[str, object]:
    try:
        mode = normalize_mode(request.form.get("mode"))
    except ValueError:
        state = _default_form_state()
        state["error"] = error_message
        return state

    if mode is None:
        state = _default_form_state()
        state["error"] = error_message
        return state

    mode_option = get_mode_option(mode)
    if mode_option is None:
        state = _default_form_state()
        state["error"] = error_message
        return state

    try:
        source_record = _optional_record(request.form.get("from_run_id"))
    except ValueError:
        source_record = None

    symptom = None
    profile = None
    if mode == SELF_SERVE_MODE:
        try:
            symptom = get_symptom_option(request.form.get("symptom_id"))
        except ValueError:
            symptom = None
        profile = _self_serve_profile(symptom["id"] if symptom else None)
    else:
        profile_id = request.form.get("profile_id") or "custom-profile"
        try:
            profile = get_profile(profile_id)
        except ValueError:
            profile = None

    selected_checks = request.form.getlist("checks") or list(
        profile.recommended_checks if profile is not None else []
    )
    targets_text = request.form.get("targets") or "\n".join(_default_target_lines(profile))
    dns_hosts_text = request.form.get("dns_hosts") or "\n".join(_default_dns_lines(profile))

    return _build_form_state(
        mode=mode,
        mode_option=mode_option,
        selected_symptom=symptom,
        selected_profile=profile,
        selected_checks=selected_checks,
        targets_text=targets_text,
        dns_hosts_text=dns_hosts_text,
        enable_ping=request.form.get("enable_ping") == "on",
        enable_trace=request.form.get("enable_trace") == "on",
        capture_raw_commands=request.form.get("capture_raw_commands") == "on",
        from_run_id=source_record.run_id if source_record is not None else None,
        bridge=_bridge_context(source_record, profile.profile_id if profile else None),
        error_message=error_message,
    )


def _build_form_state(
    *,
    mode: str,
    mode_option: dict[str, str],
    selected_symptom: dict[str, str] | None,
    selected_profile: DiagnosticProfile | None,
    selected_checks: list[str],
    targets_text: str,
    dns_hosts_text: str,
    enable_ping: bool,
    enable_trace: bool,
    capture_raw_commands: bool,
    from_run_id: str | None,
    bridge: dict[str, str] | None,
    error_message: str | None,
) -> dict[str, object]:
    plan = build_collection_plan(
        selected_checks=selected_checks,
        targets=_split_multiline_entries(targets_text),
        dns_hosts=_split_multiline_entries(dns_hosts_text),
        enable_ping=enable_ping,
        enable_trace=enable_trace,
        capture_raw_commands=capture_raw_commands,
    )
    return {
        "mode": mode,
        "mode_option": mode_option,
        "profile_id": selected_profile.profile_id if selected_profile is not None else None,
        "selected_profile": selected_profile,
        "selected_symptom": selected_symptom,
        "symptom_id": selected_symptom["id"] if selected_symptom is not None else None,
        "selected_checks": selected_checks,
        "checks_csv": ",".join(selected_checks) if selected_checks else None,
        "targets": _split_multiline_entries(targets_text),
        "dns_hosts": _split_multiline_entries(dns_hosts_text),
        "targets_text": targets_text,
        "dns_hosts_text": dns_hosts_text,
        "enable_ping": enable_ping,
        "enable_trace": enable_trace,
        "capture_raw_commands": capture_raw_commands,
        "plan": plan,
        "from_run_id": from_run_id,
        "bridge": bridge,
        "error": error_message,
    }


def _default_form_state() -> dict[str, object]:
    return {
        "mode": None,
        "mode_option": None,
        "profile_id": None,
        "selected_profile": None,
        "selected_symptom": None,
        "symptom_id": None,
        "selected_checks": [],
        "checks_csv": None,
        "targets": [],
        "dns_hosts": [],
        "targets_text": "",
        "dns_hosts_text": "",
        "enable_ping": False,
        "enable_trace": False,
        "capture_raw_commands": False,
        "plan": build_collection_plan(
            selected_checks=[],
            targets=[],
            dns_hosts=[],
            enable_ping=False,
            enable_trace=False,
            capture_raw_commands=False,
        ),
        "from_run_id": None,
        "bridge": None,
        "error": None,
    }


def _query_previous_record() -> RunSession | None:
    return _optional_record(request.args.get("from_run"))


def _profile_catalog_context() -> tuple[list[DiagnosticProfile], list[ProfileCatalogIssue]]:
    catalog = get_profile_catalog()
    return catalog.profiles, catalog.issues


def _optional_record(run_id: str | None) -> RunSession | None:
    if not run_id:
        return None
    record = _get_store().get(run_id)
    if record is None:
        raise ValueError("The earlier run is no longer available in this local session.")
    if record.status != "completed" or record.result is None:
        raise ValueError("The earlier run is still in progress. Wait for its results first.")
    return record


def _self_serve_profile(symptom_id: str | None) -> DiagnosticProfile | None:
    profile_id = resolve_self_serve_profile_id(symptom_id)
    return get_profile(profile_id) if profile_id else None


def _default_support_profile_id(source_record: RunSession | None) -> str:
    if source_record and source_record.options.profile is not None:
        return source_record.options.profile.profile_id
    return "custom-profile"


def _bridge_context(
    source_record: RunSession | None,
    current_profile_id: str | None,
) -> dict[str, str] | None:
    if source_record is None:
        return None

    result = cast(EndpointDiagnosticResult, source_record.result)
    suggested_profile_id = suggest_support_profile_id(
        result,
        symptom_id=source_record.experience.symptom_id,
        current_profile_id=(
            source_record.options.profile.profile_id
            if source_record.options.profile is not None
            else None
        ),
    )
    if current_profile_id == suggested_profile_id:
        suggestion_url = None
        suggestion_name = get_profile(suggested_profile_id).name
    else:
        suggestion_name = get_profile(suggested_profile_id).name
        suggestion_url = _support_bridge_url(
            source_record,
            suggested_profile_id=suggested_profile_id,
        )

    top_finding = result.findings[0] if result.findings else None
    headline = (
        top_finding.plain_language or top_finding.summary
        if top_finding is not None
        else "The earlier run did not confirm a major issue."
    )
    return {
        "run_id": source_record.run_id,
        "mode_label": source_record.experience.mode_label,
        "results_url": url_for("results", run_id=source_record.run_id),
        "headline": headline,
        "suggested_profile_name": suggestion_name,
        "suggested_profile_url": suggestion_url or "",
    }


def _support_bridge_url(
    record: RunSession,
    *,
    suggested_profile_id: str | None = None,
) -> str:
    result = cast(EndpointDiagnosticResult, record.result)
    profile = get_profile(
        suggested_profile_id
        or suggest_support_profile_id(
            result,
            symptom_id=record.experience.symptom_id,
            current_profile_id=(
                record.options.profile.profile_id if record.options.profile is not None else None
            ),
        )
    )
    merged_checks = _merge_checks(profile.recommended_checks, record.options.selected_checks)
    merged_targets = _merge_targets(profile.tcp_targets, list(record.options.targets))
    merged_dns_hosts = _merge_dns_hosts(profile.dns_hosts, list(record.options.dns_hosts))
    return url_for(
        "index",
        mode=SUPPORT_MODE,
        profile=profile.profile_id,
        from_run=record.run_id,
        checks=",".join(merged_checks),
        targets="\n".join(merged_targets),
        dns_hosts="\n".join(merged_dns_hosts),
        enable_ping="1" if record.options.enable_ping else "0",
        enable_trace=(
            "1"
            if record.options.enable_trace or "connectivity" in merged_checks
            else "0"
        ),
        capture_raw_commands="0",
    )


def _rerun_url(record: RunSession) -> str:
    base_params: dict[str, Any] = {
        "mode": record.experience.mode,
        "checks": ",".join(record.options.selected_checks),
        "targets": _targets_text(record.options.targets),
        "dns_hosts": "\n".join(record.options.dns_hosts),
        "enable_ping": "1" if record.options.enable_ping else "0",
        "enable_trace": "1" if record.options.enable_trace else "0",
        "capture_raw_commands": "1" if record.options.capture_raw_commands else "0",
    }
    if record.experience.mode == SELF_SERVE_MODE and record.experience.symptom_id:
        return url_for("index", symptom=record.experience.symptom_id, **base_params)
    if record.experience.mode == SUPPORT_MODE:
        return url_for(
            "index",
            profile=(
                record.options.profile.profile_id
                if record.options.profile is not None
                else "custom-profile"
            ),
            **base_params,
        )
    return url_for("index", **base_params)


def _merge_checks(primary: list[str], secondary: list[str]) -> list[str]:
    return list(OrderedDict.fromkeys([*primary, *secondary]))


def _merge_targets(primary: list[TcpTarget], secondary: list[TcpTarget]) -> list[str]:
    merged: OrderedDict[tuple[str, int], str] = OrderedDict()
    for target in [*primary, *secondary]:
        merged[(target.host, target.port)] = f"{target.host}:{target.port}"
    return list(merged.values())


def _merge_dns_hosts(primary: list[str], secondary: list[str]) -> list[str]:
    return list(OrderedDict.fromkeys([*primary, *secondary]))


def _default_target_lines(profile: DiagnosticProfile | None) -> list[str]:
    targets = (
        profile.tcp_targets
        if profile is not None and profile.tcp_targets
        else DEFAULT_TCP_TARGETS
    )
    return [f"{target.host}:{target.port}" for target in targets]


def _default_dns_lines(profile: DiagnosticProfile | None) -> list[str]:
    return list(
        profile.dns_hosts
        if profile is not None and profile.dns_hosts
        else DEFAULT_DNS_HOSTS
    )


def _split_multiline_entries(raw_text: str | None) -> list[str]:
    if not raw_text:
        return []
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


def _targets_text(targets: tuple[TcpTarget, ...] | list[TcpTarget]) -> str:
    return "\n".join(f"{target.host}:{target.port}" for target in targets)


def _resolve_redaction_level(raw_value: str | None) -> RedactionLevel:
    if raw_value == "none":
        return "none"
    if raw_value == "safe":
        return "safe"
    if raw_value == "strict":
        return "strict"
    return "safe"


def _progress_row_tone(status: str) -> str:
    if status == "passed":
        return "clear"
    if status in {"partial", "unsupported", "skipped"}:
        return "partial"
    if status == "failed":
        return "attention"
    return "not_run"


def _progress_row_summary(record: DomainExecution) -> str:
    base_summary = record.summary or "No status summary recorded."
    if record.status == "passed":
        return f"Completed successfully. {base_summary}"
    if record.status == "partial":
        return f"Completed with mixed results. {base_summary}"
    if record.status == "unsupported":
        return f"Completed with platform limits. {base_summary}"
    if record.status == "failed":
        return f"Completed with a failure to review. {base_summary}"
    if record.status == "skipped":
        return f"Completed without the optional probe. {base_summary}"
    return base_summary


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
