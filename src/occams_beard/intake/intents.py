"""Intent-driven translation from web symptom input to execution defaults."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from occams_beard.models import EndpointDiagnosticResult


@dataclass(frozen=True)
class IntakeIntent:
    """Normalized user intent that bridges UI wording and execution strategy."""

    intent_id: str
    symptom_id: str
    self_serve_profile_id: str
    support_profile_id: str


INTENT_BY_SYMPTOM: Final[dict[str, IntakeIntent]] = {
    "internet-not-working": IntakeIntent(
        intent_id="internet_outage",
        symptom_id="internet-not-working",
        self_serve_profile_id="no-internet",
        support_profile_id="no-internet",
    ),
    "apps-sites-not-loading": IntakeIntent(
        intent_id="app_path_partial_connectivity",
        symptom_id="apps-sites-not-loading",
        self_serve_profile_id="dns-issue",
        support_profile_id="internal-service-unreachable",
    ),
    "vpn-or-company-resource-issue": IntakeIntent(
        intent_id="private_resource_access",
        symptom_id="vpn-or-company-resource-issue",
        self_serve_profile_id="vpn-issue",
        support_profile_id="vpn-issue",
    ),
    "device-feels-slow": IntakeIntent(
        intent_id="endpoint_performance",
        symptom_id="device-feels-slow",
        self_serve_profile_id="device-slow",
        support_profile_id="device-slow",
    ),
    "something-else": IntakeIntent(
        intent_id="general_triage",
        symptom_id="something-else",
        self_serve_profile_id="custom-profile",
        support_profile_id="custom-profile",
    ),
}


def resolve_intake_intent(symptom_id: str | None) -> IntakeIntent | None:
    """Resolve a symptom identifier to a stable intake intent."""

    if symptom_id in {None, ""}:
        return None
    return INTENT_BY_SYMPTOM.get(symptom_id)


def resolve_self_serve_profile_id(symptom_id: str | None) -> str | None:
    """Map a self-serve symptom choice to a backing local profile."""

    intent = resolve_intake_intent(symptom_id)
    return intent.self_serve_profile_id if intent is not None else None


def suggest_support_profile_id(
    result: EndpointDiagnosticResult,
    *,
    symptom_id: str | None = None,
    current_profile_id: str | None = None,
) -> str:
    """Choose the most relevant guided-support starting profile."""

    if result.probable_fault_domain == "dns":
        return "dns-issue"
    if result.probable_fault_domain == "vpn":
        return "vpn-issue"
    if result.probable_fault_domain == "local_host":
        return "device-slow"
    if result.probable_fault_domain in {"upstream_network"}:
        return "internal-service-unreachable"
    if result.probable_fault_domain in {"local_network", "internet_edge"}:
        return "no-internet"

    intent = resolve_intake_intent(symptom_id)
    if intent is not None:
        return intent.support_profile_id
    if current_profile_id:
        return current_profile_id
    return "custom-profile"
