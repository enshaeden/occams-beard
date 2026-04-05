"""Canonical intake contract catalog.

This catalog centralizes symptom entry points, constrained internal intents,
clarification prompts, refined pathways, and downstream domain mappings.
"""

from __future__ import annotations

from occams_beard.intake.contracts import (
    ClarificationQuestion,
    IntakeContract,
    IntakeIntent,
    RefinedAnswerPathway,
    SymptomEntry,
    validate_contract,
)

_CANONICAL_INTAKE_CONTRACT = IntakeContract(
    symptoms=(
        SymptomEntry(
            key="internet-not-working",
            label="Internet not working",
            description="Websites and online apps are not connecting.",
            representative_phrases=(
                "I cannot get online",
                "everything is offline",
                "internet is down",
            ),
            intent_key="internet_connectivity_loss",
        ),
        SymptomEntry(
            key="apps-sites-not-loading",
            label="Apps or sites not loading",
            description="Some sites or sign-in flows fail while others work.",
            representative_phrases=(
                "some websites time out",
                "internal app will not load",
                "auth page keeps spinning",
            ),
            intent_key="partial_access_or_dns",
        ),
        SymptomEntry(
            key="vpn-or-company-resource-issue",
            label="VPN or company resource issue",
            description="VPN or internal-only systems are unavailable.",
            representative_phrases=(
                "VPN connects but no resources",
                "cannot reach company server",
                "intranet unavailable",
            ),
            intent_key="vpn_or_private_resource_access",
        ),
        SymptomEntry(
            key="device-feels-slow",
            label="Device feels slow",
            description="Device responsiveness is degraded.",
            representative_phrases=(
                "my laptop is very slow",
                "everything lags",
                "system feels overloaded",
            ),
            intent_key="local_performance_degradation",
        ),
        SymptomEntry(
            key="something-else",
            label="Something else",
            description="General check needed before narrowing the issue.",
            representative_phrases=(
                "not sure what is wrong",
                "need a full quick check",
                "other network problem",
            ),
            intent_key="general_triage",
        ),
        SymptomEntry(
            key="clock-or-cert-errors",
            label="Clock or certificate related errors",
            description="Sign-in or sites fail with certificate or time-related errors.",
            representative_phrases=(
                "certificate is not valid",
                "clock seems wrong",
                "secure connection fails",
            ),
            intent_key="clock_or_trust_failure",
        ),
    ),
    intents=(
        IntakeIntent(
            key="internet_connectivity_loss",
            label="Internet connectivity loss",
            description="Endpoint cannot reach public network targets.",
            representative_phrases=(
                "internet down",
                "no connectivity",
                "cannot browse anything",
            ),
            clarification_keys=("scope_of_failure", "network_change_recent"),
            pathway_keys=("baseline_connectivity", "edge_network_path"),
        ),
        IntakeIntent(
            key="partial_access_or_dns",
            label="Partial access or DNS",
            description="Some services fail while transport may still work.",
            representative_phrases=(
                "some sites work some do not",
                "name resolution issue",
                "app-specific connectivity failure",
            ),
            clarification_keys=("scope_of_failure", "dns_error_surface"),
            pathway_keys=("resolver_and_routing", "service_specific_probe"),
        ),
        IntakeIntent(
            key="vpn_or_private_resource_access",
            label="VPN or private resource access",
            description="Company-only systems unavailable with or without VPN.",
            representative_phrases=(
                "cannot access intranet",
                "VPN broken",
                "private resource unreachable",
            ),
            clarification_keys=("vpn_state", "scope_of_failure"),
            pathway_keys=("vpn_path", "service_specific_probe"),
        ),
        IntakeIntent(
            key="local_performance_degradation",
            label="Local performance degradation",
            description="Host resource pressure impacts user experience.",
            representative_phrases=(
                "device is sluggish",
                "system freezes",
                "high CPU or memory",
            ),
            clarification_keys=("degradation_pattern", "network_change_recent"),
            pathway_keys=("host_health_path", "baseline_connectivity"),
        ),
        IntakeIntent(
            key="clock_or_trust_failure",
            label="Clock or trust failure",
            description="Certificate, auth, or trust chain issues likely tied to time drift.",
            representative_phrases=(
                "certificate invalid",
                "clock mismatch",
                "TLS trust error",
            ),
            clarification_keys=("dns_error_surface", "scope_of_failure"),
            pathway_keys=("time_and_trust_path", "resolver_and_routing"),
        ),
        IntakeIntent(
            key="support_bundle_preparation",
            label="Support bundle preparation",
            description="Gather support-grade evidence for handoff.",
            representative_phrases=(
                "support asked for logs",
                "need a bundle",
                "collect diagnostics for ticket",
            ),
            clarification_keys=("bundle_depth",),
            pathway_keys=("support_handoff_path",),
        ),
        IntakeIntent(
            key="general_triage",
            label="General triage",
            description="No clear symptom category yet; run broad initial checks.",
            representative_phrases=(
                "not sure",
                "general issue",
                "start with basics",
            ),
            clarification_keys=("scope_of_failure", "degradation_pattern"),
            pathway_keys=("baseline_connectivity", "host_health_path"),
        ),
    ),
    clarification_questions=(
        ClarificationQuestion(
            key="scope_of_failure",
            prompt="Which scope best matches the issue right now?",
            options=("all_sites_and_apps", "some_sites_or_apps", "company_only_resources"),
        ),
        ClarificationQuestion(
            key="network_change_recent",
            prompt="Did this begin after changing networks, docking, or waking from sleep?",
            options=("yes", "no", "unsure"),
        ),
        ClarificationQuestion(
            key="vpn_state",
            prompt="What best describes VPN state?",
            options=("vpn_disconnected", "vpn_connected_no_access", "vpn_unstable"),
        ),
        ClarificationQuestion(
            key="degradation_pattern",
            prompt="How would you describe the slowdown pattern?",
            options=("always_slow", "slow_under_load", "intermittent"),
        ),
        ClarificationQuestion(
            key="dns_error_surface",
            prompt="Do you see DNS, certificate, or name resolution errors?",
            options=("dns_or_name_error", "certificate_or_time_error", "no_explicit_error"),
        ),
        ClarificationQuestion(
            key="bundle_depth",
            prompt="What level of artifact should be prepared for support?",
            options=("summary_only", "bundle_no_raw_commands", "bundle_with_raw_commands"),
        ),
    ),
    refined_answer_pathways=(
        RefinedAnswerPathway(
            key="baseline_connectivity",
            label="Baseline transport and reachability",
            profile_fallback_id="no-internet",
            next_domains=("network", "routing", "dns", "connectivity"),
        ),
        RefinedAnswerPathway(
            key="edge_network_path",
            label="Internet-edge and local-segment validation",
            profile_fallback_id="no-internet",
            next_domains=("network", "routing", "connectivity"),
        ),
        RefinedAnswerPathway(
            key="resolver_and_routing",
            label="Resolver and route-path isolation",
            profile_fallback_id="dns-issue",
            next_domains=("dns", "routing", "connectivity"),
        ),
        RefinedAnswerPathway(
            key="service_specific_probe",
            label="Service-specific transport and endpoint probe",
            profile_fallback_id="internal-service-unreachable",
            next_domains=("connectivity", "services", "dns"),
        ),
        RefinedAnswerPathway(
            key="vpn_path",
            label="VPN posture and split-tunnel checks",
            profile_fallback_id="vpn-issue",
            next_domains=("network", "routing", "vpn", "services"),
        ),
        RefinedAnswerPathway(
            key="host_health_path",
            label="Host health and local pressure checks",
            profile_fallback_id="device-slow",
            next_domains=("host", "resources", "storage"),
        ),
        RefinedAnswerPathway(
            key="time_and_trust_path",
            label="Clock, trust, and identity prerequisites",
            profile_fallback_id="custom-profile",
            next_domains=("time", "dns", "connectivity"),
        ),
        RefinedAnswerPathway(
            key="support_handoff_path",
            label="Support handoff artifact preparation",
            profile_fallback_id="custom-profile",
            next_domains=("host", "network", "routing", "dns", "connectivity", "services"),
        ),
    ),
)

validate_contract(_CANONICAL_INTAKE_CONTRACT)


def get_intake_contract() -> IntakeContract:
    """Return the canonical intent-driven intake contract."""

    return _CANONICAL_INTAKE_CONTRACT
