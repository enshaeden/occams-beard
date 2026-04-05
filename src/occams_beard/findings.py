"""Deterministic findings engine for host and network diagnostics."""

from __future__ import annotations

from occams_beard.findings_network import (
    evaluate_dns_path,
    evaluate_network_path,
    evaluate_trace_results,
)
from occams_beard.findings_resources import (
    evaluate_hardware_health,
    evaluate_resource_pressure,
)
from occams_beard.findings_services import evaluate_service_path, evaluate_vpn_path
from occams_beard.findings_time import evaluate_time_state
from occams_beard.models import CollectedFacts, Finding

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "info": 0}


def evaluate_findings(facts: CollectedFacts) -> tuple[list[Finding], str]:
    """Evaluate deterministic findings and derive a probable fault domain."""

    findings = _evaluate_all_findings(facts)
    return _finalize_findings(
        findings, baseline_summary="The collected facts did not match any major fault rule."
    )


def evaluate_selected_findings(
    facts: CollectedFacts,
    selected_checks: list[str],
    *,
    issue_category: str | None = None,
) -> tuple[list[Finding], str]:
    """Evaluate only the rules supported by the completed diagnostic domains."""

    enabled = set(selected_checks)
    findings: list[Finding] = []

    if {"network", "routing", "connectivity"} & enabled:
        findings.extend(evaluate_network_path(facts))
    if {"dns", "connectivity"} <= enabled:
        findings.extend(evaluate_dns_path(facts))
    if "time" in enabled:
        findings.extend(evaluate_time_state(facts, enabled_checks=enabled))
    if {"resources", "storage"} & enabled:
        findings.extend(
            evaluate_resource_pressure(
                facts,
                enabled_checks=enabled,
                issue_category=issue_category,
            )
        )
        findings.extend(evaluate_hardware_health(facts))
    if "connectivity" in enabled:
        findings.extend(evaluate_trace_results(facts))
    if "services" in enabled:
        findings.extend(evaluate_service_path(facts))
    if {"vpn", "services"} <= enabled:
        findings.extend(evaluate_vpn_path(facts))

    return _finalize_findings(
        findings, baseline_summary="The collected facts did not match any enabled fault rule."
    )


def _evaluate_all_findings(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(evaluate_network_path(facts))
    findings.extend(evaluate_dns_path(facts))
    findings.extend(
        evaluate_time_state(
            facts,
            enabled_checks={"time", "routing", "dns", "connectivity", "services"},
        )
    )
    findings.extend(evaluate_resource_pressure(facts))
    findings.extend(evaluate_hardware_health(facts))
    findings.extend(evaluate_trace_results(facts))
    findings.extend(evaluate_service_path(facts))
    findings.extend(evaluate_vpn_path(facts))
    return findings


def _finalize_findings(
    findings: list[Finding],
    baseline_summary: str,
) -> tuple[list[Finding], str]:
    if not findings:
        findings.append(
            Finding(
                identifier="healthy-baseline",
                severity="info",
                title="No major diagnostic findings detected",
                summary=baseline_summary,
                evidence=[
                    (
                        "Deterministic rule evaluation completed without "
                        "triggering supported fault signatures."
                    )
                ],
                probable_cause=(
                    "No major failure domain was identified from the collected evidence."
                ),
                fault_domain="healthy",
                confidence=0.8,
            )
        )

    findings.sort(
        key=lambda item: (SEVERITY_RANK[item.severity], item.confidence),
        reverse=True,
    )
    probable_fault_domain = findings[0].fault_domain if findings else "unknown"
    return findings, probable_fault_domain
