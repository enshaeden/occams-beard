"""Route registration for the local Flask troubleshooting interface."""

from __future__ import annotations

from typing import cast
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

from occams_beard.execution import planned_execution_step_count
from occams_beard.models import EndpointDiagnosticResult
from occams_beard.web.forms import (
    default_form_state,
    form_state_from_request,
    page_title,
    profile_catalog_context,
    query_form_state,
    request_error_form_state,
    rerun_url,
    resolve_redaction_level,
    support_bridge_url,
)
from occams_beard.web.presentation.catalog import (
    SELF_SERVE_MODE,
    list_mode_options,
    list_symptom_options,
)
from occams_beard.web.presentation.results import build_results_view
from occams_beard.web.progress import build_progress_view, initial_progress_execution
from occams_beard.web.sessions import (
    RunExperience,
    RunSession,
    get_completed_record_or_409,
    get_session_or_404,
    get_store,
    start_run_thread,
)


def register_web_routes(app: Flask) -> None:
    """Register the local interface routes on the provided Flask app."""

    @app.get("/")
    def index():
        try:
            form_state = query_form_state()
        except ValueError as exc:
            form_state = default_form_state()
            form_state["error"] = str(exc)
        profiles, profile_catalog_issues = profile_catalog_context()
        return render_template(
            "index.html",
            mode_options=list_mode_options(),
            symptom_options=list_symptom_options(),
            profiles=profiles,
            profile_catalog_issues=profile_catalog_issues,
            form_state=form_state,
            page_title=page_title(cast(str | None, form_state["mode"])),
        )

    @app.get("/self-serve/plan")
    def self_serve_plan():
        try:
            form_state = query_form_state()
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

    @app.get("/health/runtime")
    def health_runtime():
        payload = dict(current_app.config["RUNTIME_METADATA"])
        payload["server_origin"] = request.host_url.rstrip("/")
        return jsonify(payload)

    @app.post("/run")
    def run():
        try:
            form_state = form_state_from_request()
        except ValueError as exc:
            form_state = request_error_form_state(str(exc))
            profiles, profile_catalog_issues = profile_catalog_context()
            return (
                render_template(
                    "index.html",
                    mode_options=list_mode_options(),
                    symptom_options=list_symptom_options(),
                    profiles=profiles,
                    profile_catalog_issues=profile_catalog_issues,
                    form_state=form_state,
                    page_title=page_title(cast(str | None, form_state["mode"])),
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
            profiles, profile_catalog_issues = profile_catalog_context()
            return (
                render_template(
                    "index.html",
                    mode_options=list_mode_options(),
                    symptom_options=list_symptom_options(),
                    profiles=profiles,
                    profile_catalog_issues=profile_catalog_issues,
                    form_state=form_state,
                    page_title=page_title(cast(str | None, form_state["mode"])),
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
            progress_execution=initial_progress_execution(options),
            current_domain="host",
            completed_count=0,
            total_count=planned_execution_step_count(options),
            completed_steps_by_domain={},
        )
        get_store().create(session)
        app_object = current_app._get_current_object()  # type: ignore[attr-defined]
        start_run_thread(cast(Flask, app_object), run_id)
        return redirect(url_for("run_progress", run_id=run_id))

    @app.get("/runs/<run_id>")
    def run_progress(run_id: str):
        session = get_session_or_404(run_id)
        if session.status == "completed":
            return redirect(url_for("results", run_id=run_id))
        return render_template(
            "run_progress.html",
            page_title=f"{session.experience.mode_label} Progress",
            session=session,
            view=build_progress_view(session),
            rerun_url=rerun_url(session),
        )

    @app.get("/runs/<run_id>/status")
    def run_status(run_id: str):
        session = get_session_or_404(run_id)
        payload = build_progress_view(session)
        payload["results_url"] = url_for("results", run_id=run_id)
        payload["rerun_url"] = rerun_url(session)
        return jsonify(payload)

    @app.get("/results/<run_id>")
    def results(run_id: str):
        session = get_session_or_404(run_id)
        if session.status != "completed" or session.result is None:
            return redirect(url_for("run_progress", run_id=run_id))
        previous_results_url = (
            url_for("results", run_id=session.experience.previous_run_id)
            if session.experience.previous_run_id
            and get_store().get_completed(session.experience.previous_run_id)
            else None
        )
        continue_with_support_url = None
        if session.experience.mode == SELF_SERVE_MODE:
            continue_with_support_url = support_bridge_url(session)
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
            rerun_url=rerun_url(session),
            view=view,
        )

    @app.get("/results/<run_id>/result.json")
    def download_json(run_id: str):
        record = get_completed_record_or_409(run_id)
        return Response(
            cast(str, record.json_text) + "\n",
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename=occams-beard-{run_id}.json"},
        )

    @app.get("/results/<run_id>/support-bundle.zip")
    def download_support_bundle(run_id: str):
        from occams_beard.support_bundle import build_support_bundle_archive

        record = get_completed_record_or_409(run_id)
        redaction_level = resolve_redaction_level(request.args.get("redaction_level"))
        include_raw_command_capture = request.args.get("include_raw") == "1"
        body = build_support_bundle_archive(
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
