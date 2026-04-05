"""Assemble the final diagnostics result from collected state."""

from __future__ import annotations

import platform as python_platform
from typing import TYPE_CHECKING, cast

from occams_beard import __version__
from occams_beard.execution import build_execution_records
from occams_beard.explanations import build_guided_experience, enrich_findings
from occams_beard.findings import evaluate_selected_findings
from occams_beard.models import (
    EndpointDiagnosticResult,
    FaultDomain,
    Metadata,
    PlatformInfo,
    RawCommandCapture,
)
from occams_beard.schema import RESULT_SCHEMA_VERSION
from occams_beard.utils.time import utc_now_iso

if TYPE_CHECKING:
    from occams_beard.run_context import DiagnosticsRunContext
    from occams_beard.run_options import DiagnosticsRunOptions


def assemble_endpoint_result(
    options: DiagnosticsRunOptions,
    context: DiagnosticsRunContext,
    *,
    elapsed_ms: int,
    raw_command_capture: list[RawCommandCapture],
) -> EndpointDiagnosticResult:
    """Build the stable endpoint result contract from the completed run context."""

    facts = context.current_facts()
    findings, probable_fault_domain = evaluate_selected_findings(
        facts,
        options.selected_checks,
        issue_category=options.profile.issue_category if options.profile else None,
    )
    findings = enrich_findings(findings)
    execution = build_execution_records(facts, options, context.warnings, context.durations_ms)
    guided_experience = build_guided_experience(findings, execution, options.profile)

    return EndpointDiagnosticResult(
        metadata=Metadata(
            project_name="occams-beard",
            version=__version__,
            generated_at=utc_now_iso(),
            elapsed_ms=elapsed_ms,
            selected_checks=options.selected_checks,
            profile_id=options.profile.profile_id if options.profile else None,
            profile_name=options.profile.name if options.profile else None,
            issue_category=options.profile.issue_category if options.profile else None,
        ),
        platform=PlatformInfo(
            system=python_platform.system(),
            release=python_platform.release(),
            version=python_platform.version(),
            machine=python_platform.machine(),
            python_version=python_platform.python_version(),
        ),
        facts=facts,
        schema_version=RESULT_SCHEMA_VERSION,
        findings=findings,
        probable_fault_domain=cast(FaultDomain, probable_fault_domain),
        warnings=list(context.warnings),
        execution=execution,
        guided_experience=guided_experience,
        raw_command_capture=raw_command_capture,
    )
