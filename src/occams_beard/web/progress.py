"""Progress-state helpers for local diagnostics runs."""

from __future__ import annotations

import time

from occams_beard.defaults import DEFAULT_CHECKS
from occams_beard.domain_registry import domain_creates_network_egress
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
                creates_network_egress=domain_creates_network_egress(domain, options),
            )
        )
    return progress_execution


def build_progress_view(session) -> dict[str, object]:
    """Build the view model for the live local progress page."""

    total_count = session.total_count or planned_execution_step_count(session.options)
    completed_count = min(session.completed_count, total_count)
    progress_percent = int((completed_count / total_count) * 100) if total_count else 0
    elapsed_seconds = _elapsed_seconds(session)
    elapsed_label = _elapsed_label(elapsed_seconds)
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
            f"Currently running: {current_domain_label}. {current_substep_label}."
            if current_domain_label is not None and current_substep_label is not None
            else (
                f"Currently running: {current_domain_label}."
                if current_domain_label is not None
            else "Preparing the next step."
            )
        )

    update_notice = (
        "Still running normally. This page updates automatically."
        if session.status in {"queued", "running"} and elapsed_seconds >= 20
        else "This page updates automatically."
    )
    presence_notice = (
        "You can leave this page open or come back when results are ready."
        if session.status in {"queued", "running"}
        else "Results stay available locally on this device."
    )
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
                    f"{completed_steps}/{total_steps}"
                    if record.selected and total_steps
                    else "Optional"
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
                "active": bool(
                    session.status in {"queued", "running"}
                    and record.selected
                    and record.domain == session.current_domain
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
        "elapsed_seconds": elapsed_seconds,
        "elapsed_label": elapsed_label,
        "update_notice": update_notice,
        "presence_notice": presence_notice,
        "mode_notice": mode_notice,
        "live_status_message": _live_status_message(
            status=session.status,
            current_domain_label=current_domain_label,
            completed_count=completed_count,
            total_count=total_count,
        ),
        "rows": rows,
    }


def _elapsed_seconds(session) -> int:
    if session.status == "completed" and session.result is not None:
        return max(0, int(session.result.metadata.elapsed_ms / 1000))
    return max(0, int(time.monotonic() - session.started_at_monotonic))


def _elapsed_label(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {remainder:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _live_status_message(
    *,
    status: str,
    current_domain_label: str | None,
    completed_count: int,
    total_count: int,
) -> str:
    if status == "failed":
        return "Run stopped. Review the error details before trying again."
    if status == "completed":
        return "Results are ready."
    if current_domain_label:
        return (
            f"{current_domain_label} is active. "
            f"{completed_count} of {total_count} planned steps complete."
        )
    return f"Preparing the next step. {completed_count} of {total_count} planned steps complete."


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
