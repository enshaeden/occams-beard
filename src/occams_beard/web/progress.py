"""Progress-state helpers for local diagnostics runs."""

from __future__ import annotations

from occams_beard.domain_registry import NETWORK_EGRESS_DOMAINS
from occams_beard.defaults import DEFAULT_CHECKS
from occams_beard.execution import (
    DOMAIN_LABELS,
    next_execution_step_label,
    planned_execution_step_breakdown,
    planned_execution_step_count,
)
from occams_beard.models import DomainExecution
from occams_beard.runner import DiagnosticsRunOptions
from occams_beard.web.presentation.catalog import SELF_SERVE_MODE


def initial_progress_execution(options: DiagnosticsRunOptions) -> list[DomainExecution]:
    """Build queued execution records before the runner starts emitting updates."""

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
                creates_network_egress=domain in NETWORK_EGRESS_DOMAINS,
            )
        )
    return progress_execution


def build_progress_view(session) -> dict[str, object]:
    """Build the view model for the live local progress page."""

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
