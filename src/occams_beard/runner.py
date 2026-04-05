"""Shared diagnostics execution service for CLI and local app flows."""

from __future__ import annotations

import logging
import time
from contextlib import nullcontext
from typing import cast

from occams_beard.domain_registry import build_execution_plan
from occams_beard.models import EndpointDiagnosticResult, RawCommandCapture
from occams_beard.result_builder import assemble_endpoint_result
from occams_beard.run_context import DiagnosticsRunContext, ProgressCallback
from occams_beard.run_options import DiagnosticsRunOptions, build_run_options
from occams_beard.utils.subprocess import capture_command_output

LOGGER = logging.getLogger(__name__)

__all__ = ["DiagnosticsRunOptions", "build_run_options", "run_diagnostics"]


def run_diagnostics(
    options: DiagnosticsRunOptions,
    *,
    progress_callback: ProgressCallback | None = None,
) -> EndpointDiagnosticResult:
    """Execute diagnostics for the provided validated options."""

    start = time.perf_counter()
    execution_plan = build_execution_plan(options)
    run_context = DiagnosticsRunContext(
        options=options,
        execution_plan=execution_plan,
        progress_callback=progress_callback,
    )
    capture_context = (
        capture_command_output()
        if options.capture_raw_commands
        else nullcontext(cast(list[RawCommandCapture], []))
    )

    LOGGER.info(
        "Running endpoint diagnostics for checks: %s",
        ", ".join(options.selected_checks),
    )
    LOGGER.debug(
        (
            "Diagnostics input summary: tcp_targets=%d dns_hosts=%d "
            "enable_ping=%s enable_trace=%s enable_time_skew_check=%s "
            "profile=%s raw_capture=%s"
        ),
        len(options.targets),
        len(options.dns_hosts),
        options.enable_ping,
        options.enable_trace,
        options.enable_time_skew_check,
        options.profile.profile_id if options.profile else None,
        options.capture_raw_commands,
    )

    with capture_context as raw_command_capture:
        for planned_domain in execution_plan:
            planned_domain.definition.execute(options, run_context)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return assemble_endpoint_result(
        options,
        run_context,
        elapsed_ms=elapsed_ms,
        raw_command_capture=list(raw_command_capture),
    )
