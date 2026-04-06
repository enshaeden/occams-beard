"""In-memory session tracking for the local web diagnostics flow."""

from __future__ import annotations

import inspect
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock, Thread
from typing import Any, Literal, cast

from flask import Flask, abort, current_app

from occams_beard.execution import planned_execution_step_breakdown, planned_execution_step_count
from occams_beard.models import DomainExecution, EndpointDiagnosticResult
from occams_beard.runner import DiagnosticsRunOptions
from occams_beard.serializers import to_json_text

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
    started_at_monotonic: float = field(default_factory=time.monotonic)


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


def get_store() -> RecentRunsStore:
    """Return the app-level recent-run store."""

    return cast(RecentRunsStore, current_app.config["RUN_RESULTS_STORE"])


def get_session_or_404(run_id: str) -> RunSession:
    """Return a local run session or raise a 404 response."""

    session = get_store().get(run_id)
    if session is None:
        abort(404)
    return session


def get_completed_record_or_409(run_id: str) -> RunSession:
    """Return a completed run session or raise a 409 response."""

    session = get_session_or_404(run_id)
    if session.status != "completed" or session.result is None or session.json_text is None:
        abort(409, description="This run is not complete yet.")
    return session


def start_run_thread(app: Flask, run_id: str) -> None:
    """Launch the shared runner in a background thread for the local UI."""

    worker = Thread(
        target=_run_session,
        args=(app, run_id),
        daemon=True,
        name=f"occams-beard-run-{run_id[:8]}",
    )
    worker.start()


def _run_session(app: Flask, run_id: str) -> None:
    with app.app_context():
        session = get_store().get(run_id)
        if session is None:
            return

        def progress_callback(
            progress_execution: list[DomainExecution],
            active_domain: str | None,
            completed_count: int,
            total_count: int,
            completed_steps_by_domain: dict[str, int],
        ) -> None:
            get_store().update_progress(
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
            get_store().fail(run_id, str(exc))
            return
        except Exception:
            current_app.logger.exception("Diagnostics run %s failed", run_id)
            get_store().fail(
                run_id,
                (
                    "The run stopped before results were ready. "
                    "Try again or continue with support if the issue keeps happening."
                ),
            )
            return

        get_store().complete(
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
