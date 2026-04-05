"""Intent-to-domain mapping for self-serve intake scope selection."""

from __future__ import annotations

from dataclasses import dataclass

from occams_beard.defaults import DEFAULT_CHECKS
from occams_beard.intake.clarification_models import DecisionContext
from occams_beard.intake.contracts import IntakeContract
from occams_beard.intake.resolver import IntakeResolution

_DOMAIN_TO_CHECKS = {
    "host": ("host",),
    "time": ("time",),
    "resources": ("resources",),
    "storage": ("storage",),
    "network": ("network",),
    "routing": ("routing",),
    "dns": ("dns",),
    "connectivity": ("connectivity",),
    "vpn": ("vpn",),
    "services": ("services",),
}

_INTENT_PROFILE_SUGGESTIONS = {
    "internet_connectivity_loss": "no-internet",
    "partial_access_or_dns": "dns-issue",
    "vpn_or_private_resource_access": "vpn-issue",
    "local_performance_degradation": "device-slow",
    "clock_or_trust_failure": "custom-profile",
    "support_bundle_preparation": "custom-profile",
    "general_triage": "custom-profile",
}

_INTENT_DEFAULT_DOMAINS = {
    "internet_connectivity_loss": ("network", "routing", "dns", "connectivity"),
    "partial_access_or_dns": ("dns", "routing", "connectivity", "services"),
    "vpn_or_private_resource_access": (
        "network",
        "routing",
        "vpn",
        "services",
        "dns",
        "connectivity",
    ),
    "local_performance_degradation": ("resources", "storage", "network", "routing"),
    "clock_or_trust_failure": ("time", "dns", "connectivity", "network"),
    "support_bundle_preparation": (
        "host",
        "network",
        "routing",
        "dns",
        "connectivity",
        "services",
    ),
    "general_triage": ("network", "routing", "dns", "connectivity", "resources"),
}


@dataclass(frozen=True, slots=True)
class DomainMappingResult:
    """Resolved execution scope for intake-driven self-serve diagnostics."""

    selected_checks: tuple[str, ...]
    suggested_profile_id: str | None
    fallback_mode: str | None = None
    selected_domains: tuple[str, ...] = ()
    rationale: str = "unspecified"



def map_intake_to_scope(
    *,
    resolution: IntakeResolution,
    contract: IntakeContract,
    context: DecisionContext | None = None,
) -> DomainMappingResult:
    """Convert intake resolution and optional refined context into run scope."""

    intent_key = resolution.primary_intent
    if not intent_key:
        return DomainMappingResult(
            selected_checks=tuple(DEFAULT_CHECKS),
            suggested_profile_id="custom-profile",
            fallback_mode="general_triage",
            selected_domains=(),
            rationale="fallback_general_triage_no_intent",
        )

    domains, rationale = _domains_from_context_or_intent(
        intent_key=intent_key,
        contract=contract,
        context=context,
    )
    checks = _checks_for_domains(domains)
    if not checks:
        return DomainMappingResult(
            selected_checks=tuple(DEFAULT_CHECKS),
            suggested_profile_id="custom-profile",
            fallback_mode="custom_profile",
            selected_domains=domains,
            rationale="fallback_default_checks_unknown_domains",
        )

    suggested_profile_id = _suggested_profile_for_context(intent_key, context)
    return DomainMappingResult(
        selected_checks=checks,
        suggested_profile_id=suggested_profile_id,
        selected_domains=domains,
        rationale=rationale,
    )


def _domains_from_context_or_intent(
    *,
    intent_key: str,
    contract: IntakeContract,
    context: DecisionContext | None,
) -> tuple[tuple[str, ...], str]:
    if context is not None and context.next_domains:
        return context.next_domains, "clarification_pathway_domains"

    intent = next((item for item in contract.intents if item.key == intent_key), None)
    if intent and intent.pathway_keys:
        pathway = next(
            (
                item
                for item in contract.refined_answer_pathways
                if item.key == intent.pathway_keys[0]
            ),
            None,
        )
        if pathway is not None:
            return pathway.next_domains, "intent_primary_pathway_domains"

    default_domains = _INTENT_DEFAULT_DOMAINS.get(intent_key, ())
    if default_domains:
        return default_domains, "intent_default_domains"
    return (), "intent_unknown_domains"



def _checks_for_domains(domains: tuple[str, ...]) -> tuple[str, ...]:
    checks: list[str] = []
    seen: set[str] = set()
    for domain in domains:
        # Unknown domains are intentionally ignored.
        for check in _DOMAIN_TO_CHECKS.get(domain, ()):
            if check in seen:
                continue
            seen.add(check)
            checks.append(check)
    return tuple(checks)



def _suggested_profile_for_context(intent_key: str, context: DecisionContext | None) -> str | None:
    if context is not None and context.profile_fallback_id:
        return context.profile_fallback_id
    return _INTENT_PROFILE_SUGGESTIONS.get(intent_key, "custom-profile")
