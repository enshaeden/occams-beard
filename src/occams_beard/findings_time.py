"""Time-focused deterministic findings rules."""

from __future__ import annotations

from occams_beard.findings_common import (
    dedupe_preserve_order,
    format_utc_offset,
    network_explanation_not_supported,
    network_health_evidence,
)
from occams_beard.models import CollectedFacts, Finding


def evaluate_time_state(
    facts: CollectedFacts,
    *,
    enabled_checks: set[str],
) -> list[Finding]:
    time_state = facts.time
    if time_state is None:
        return []

    findings: list[Finding] = []
    skew_check = time_state.skew_check
    absolute_skew_seconds = (
        skew_check.absolute_skew_seconds if skew_check is not None else None
    )
    weakens_network_explanation = network_explanation_not_supported(
        facts,
        enabled_checks=enabled_checks,
    )

    if absolute_skew_seconds is not None and absolute_skew_seconds >= 300:
        findings.append(
            Finding(
                identifier="system-clock-materially-inaccurate",
                severity="high" if absolute_skew_seconds >= 900 else "medium",
                title="System clock appears materially inaccurate",
                summary=(
                    "Measured clock skew is large enough that secure sign-in, certificate "
                    "validation, or time-bounded service access may fail."
                ),
                evidence=time_skew_evidence(
                    facts,
                    include_network_context=weakens_network_explanation,
                ),
                probable_cause=(
                    "The local system clock differs materially from the bounded external "
                    "reference, so local time state is a credible cause of secure-service or "
                    "authentication failures."
                ),
                fault_domain="local_host",
                confidence=0.93 if absolute_skew_seconds >= 900 else 0.87,
            )
        )
    elif absolute_skew_seconds is not None and absolute_skew_seconds >= 120:
        findings.append(
            Finding(
                identifier="local-time-may-impact-secure-service-access",
                severity="medium",
                title="Local time may impact secure service access",
                summary=(
                    "Measured clock skew is elevated enough that time-sensitive sign-in, TLS, "
                    "or certificate checks may become unreliable."
                ),
                evidence=time_skew_evidence(
                    facts,
                    include_network_context=weakens_network_explanation,
                ),
                probable_cause=(
                    "The local clock is not aligned closely enough with the bounded reference "
                    "to rule out time-based failures."
                ),
                fault_domain="local_host",
                confidence=0.82,
            )
        )

    if time_state.timezone_offset_consistent is False:
        findings.append(
            Finding(
                identifier="timezone-configuration-inconsistent",
                severity="low",
                title="Timezone configuration appears inconsistent with the observed offset",
                summary=(
                    "The collected timezone identifier does not match the offset observed in the "
                    "current local clock snapshot."
                ),
                evidence=timezone_consistency_evidence(time_state),
                probable_cause=(
                    "Local timezone configuration may be overridden or inconsistent, which can "
                    "make time-based failures harder to interpret."
                ),
                fault_domain="local_host",
                confidence=0.85,
            )
        )

    if skew_check is not None and skew_check.status not in {"not_run", "checked"}:
        findings.append(
            Finding(
                identifier="insufficient-clock-drift-evidence",
                severity="info",
                title="Clock drift could not be confirmed conclusively",
                summary=(
                    "The run captured local time state, but the bounded external reference did "
                    "not produce a conclusive skew result."
                ),
                evidence=inconclusive_time_evidence(time_state),
                probable_cause=(
                    "The current snapshot does not have enough verified external reference data "
                    "to confirm or dismiss material clock drift."
                ),
                fault_domain="healthy",
                confidence=0.72,
            )
        )
    elif (
        skew_check is not None
        and skew_check.status == "checked"
        and absolute_skew_seconds is not None
        and absolute_skew_seconds < 120
        and time_state.timezone_offset_consistent is not False
    ):
        findings.append(
            Finding(
                identifier="no-significant-time-issue",
                severity="info",
                title="No major time-related issue was detected from the collected evidence",
                summary=(
                    "The local clock stayed close to the bounded external reference and the "
                    "timezone state did not show a strong inconsistency."
                ),
                evidence=time_skew_evidence(
                    facts,
                    include_network_context=False,
                ),
                probable_cause=(
                    "The current evidence does not support local clock skew or timezone state as "
                    "a dominant cause of the issue."
                ),
                fault_domain="healthy",
                confidence=0.84,
            )
        )

    return findings


def time_skew_evidence(
    facts: CollectedFacts,
    *,
    include_network_context: bool,
) -> list[str]:
    time_state = facts.time
    if time_state is None or time_state.skew_check is None:
        return ["Local clock skew was not collected in this run."]

    skew_check = time_state.skew_check
    evidence = [
        f"Local time snapshot is {time_state.local_time_iso}.",
        f"UTC time snapshot is {time_state.utc_time_iso}.",
        (
            "Timezone is "
            f"{time_state.timezone_identifier} "
            f"({time_state.timezone_name or 'unknown'})."
            if time_state.timezone_identifier is not None
            else f"Timezone name is {time_state.timezone_name or 'unknown'}."
        ),
        (
            "Observed UTC offset is "
            f"{format_utc_offset(time_state.utc_offset_minutes)}."
            if time_state.utc_offset_minutes is not None
            else "Observed UTC offset was not available."
        ),
        (
            f"Bounded reference {skew_check.reference_label} reported "
            f"{skew_check.reference_time_iso}."
            if skew_check.reference_time_iso is not None
            else (
                "The bounded reference did not report a usable time value."
                if skew_check.status != "not_run"
                else "The bounded external reference was not used in this run."
            )
        ),
    ]
    if skew_check.skew_seconds is not None and skew_check.absolute_skew_seconds is not None:
        evidence.append(
            "Measured clock skew is "
            f"{skew_check.skew_seconds:.1f} seconds "
            f"(absolute {skew_check.absolute_skew_seconds:.1f} seconds)."
        )
    if include_network_context:
        evidence.extend(
            network_health_evidence(
                facts,
                enabled_checks={"routing", "dns", "connectivity"},
            )
        )
    return dedupe_preserve_order(evidence)


def timezone_consistency_evidence(time_state) -> list[str]:
    evidence = [
        f"Local time snapshot is {time_state.local_time_iso}.",
        (
            f"Timezone identifier is {time_state.timezone_identifier} "
            f"({time_state.timezone_identifier_source or 'unknown source'})."
            if time_state.timezone_identifier is not None
            else "Timezone identifier was not exposed on this endpoint."
        ),
        (
            "Observed UTC offset is "
            f"{format_utc_offset(time_state.utc_offset_minutes)}."
            if time_state.utc_offset_minutes is not None
            else "Observed UTC offset was not available."
        ),
        "Timezone identifier consistency check returned false.",
    ]
    return evidence


def inconclusive_time_evidence(time_state) -> list[str]:
    evidence = [
        f"Local time snapshot is {time_state.local_time_iso}.",
        (
            f"Timezone identifier is {time_state.timezone_identifier}."
            if time_state.timezone_identifier is not None
            else "Timezone identifier was not exposed on this endpoint."
        ),
    ]
    if time_state.skew_check is not None:
        evidence.append(
            "Bounded external skew check status is "
            f"{time_state.skew_check.status}: {time_state.skew_check.error or 'unknown-error'}."
        )
    return evidence
