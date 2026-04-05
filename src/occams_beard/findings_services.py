"""Service- and VPN-focused deterministic findings rules."""

from __future__ import annotations

from occams_beard.findings_common import format_service_targets
from occams_beard.models import CollectedFacts, Finding, ServiceCheck, VpnSignal
from occams_beard.utils.validation import is_private_or_loopback_host


def evaluate_service_path(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    public_service_checks = [
        check
        for check in facts.services.checks
        if not is_private_or_loopback_host(check.target.host)
    ]
    failed_public_services = [check for check in public_service_checks if not check.success]
    successful_public_services = [check for check in public_service_checks if check.success]
    successful_service_targets = format_service_targets(successful_public_services)
    failed_service_targets = format_service_targets(failed_public_services)

    if (
        facts.connectivity.internet_reachable
        and failed_public_services
        and not successful_public_services
    ):
        findings.append(
            Finding(
                identifier="internet-ok-selected-service-failure",
                severity="medium",
                title="Generic internet reachability works but selected service checks fail",
                summary=(
                    "Baseline external path checks succeeded, but every "
                    "configured public service check failed."
                ),
                evidence=[
                    "Generic internet reachability checks succeeded.",
                    (
                        "Failed configured public services: "
                        f"{format_service_targets(failed_public_services)}."
                    ),
                ],
                probable_cause=(
                    "The failure is more likely isolated to the intended "
                    "service path, intermediate policy control, or the target "
                    "service itself than to general internet access."
                ),
                fault_domain="upstream_network",
                confidence=0.79,
            )
        )

    if successful_public_services and failed_public_services:
        findings.append(
            Finding(
                identifier="mixed-service-results",
                severity="low",
                title="Configured service reachability is inconsistent",
                summary=(
                    "Some intended service checks succeeded while others "
                    "failed, which suggests target-specific policy or "
                    "availability differences."
                ),
                evidence=[
                    f"Successful configured services: {successful_service_targets}.",
                    f"Failed configured services: {failed_service_targets}.",
                ],
                probable_cause=(
                    "The endpoint retains some application reachability, but "
                    "selective filtering, service-side health, or "
                    "environment-specific policy may be affecting individual "
                    "targets."
                ),
                fault_domain="upstream_network",
                confidence=0.61,
                heuristic=True,
            )
        )

    return findings


def evaluate_vpn_path(facts: CollectedFacts) -> list[Finding]:
    findings: list[Finding] = []
    if not facts.vpn.signals:
        return findings

    private_service_failures = [
        check
        for check in facts.services.checks
        if not check.success and is_private_or_loopback_host(check.target.host)
    ]
    if private_service_failures:
        route_summary = facts.network.route_summary
        confidence = max(signal.confidence for signal in facts.vpn.signals)
        if route_summary.default_interface and any(
            signal.interface_name == route_summary.default_interface for signal in facts.vpn.signals
        ):
            confidence = max(confidence, 0.82)

        findings.append(
            Finding(
                identifier="vpn-signal-private-resource-failure",
                severity="medium",
                title="VPN or tunnel appears active while private targets remain unreachable",
                summary=(
                    "A VPN-like interface is present, but private resource checks still failed."
                ),
                evidence=vpn_evidence(
                    facts.vpn.signals, private_service_failures, route_summary.default_interface
                ),
                probable_cause=(
                    "The tunnel may be established, but its routes, security "
                    "policy, or remote network path may be incomplete."
                ),
                fault_domain="vpn",
                confidence=round(confidence, 2),
                heuristic=True,
            )
        )
    return findings


def vpn_evidence(
    signals: list[VpnSignal],
    failures: list[ServiceCheck],
    default_interface: str | None,
) -> list[str]:
    evidence = [
        (
            f"VPN heuristic matched interface {signal.interface_name} "
            f"({signal.signal_type}, confidence {signal.confidence:.2f}, "
            f"{signal.address_count} usable address{'es' if signal.address_count != 1 else ''})."
        )
        for signal in signals
    ]
    if default_interface:
        evidence.append(f"Default route uses interface {default_interface}.")
    evidence.extend(
        (
            f"Private target {check.target.host}:{check.target.port} failed "
            f"with {check.error or 'an unknown error'}."
        )
        for check in failures
    )
    return evidence
