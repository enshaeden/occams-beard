"""Mode and symptom metadata for the local troubleshooting experience."""

from __future__ import annotations

from occams_beard.models import EndpointDiagnosticResult

SELF_SERVE_MODE = "self-serve"
SUPPORT_MODE = "support"

MODE_OPTIONS = (
    {
        "id": SELF_SERVE_MODE,
        "label": "Check My Device",
        "description": (
            "Start with safe checks and plain-language results. You do not need "
            "to know networking terms to use this path."
        ),
        "badge": "Employee-safe",
    },
    {
        "id": SUPPORT_MODE,
        "label": "Work With Support",
        "description": (
            "Use this when IT or support asked for deeper testing, a specific "
            "profile, or a support-ready bundle."
        ),
        "badge": "Technician-directed",
    },
)

SYMPTOM_OPTIONS = (
    {
        "id": "internet-not-working",
        "label": "Internet not working",
        "description": (
            "Websites and online apps are not connecting, or everything looks offline."
        ),
        "profile_id": "no-internet",
        "support_profile_id": "no-internet",
    },
    {
        "id": "apps-sites-not-loading",
        "label": "Apps or sites not loading",
        "description": (
            "Some apps, sites, or sign-in pages stall, fail, or only partly load."
        ),
        "profile_id": "dns-issue",
        "support_profile_id": "internal-service-unreachable",
    },
    {
        "id": "vpn-or-company-resource-issue",
        "label": "VPN or company resource issue",
        "description": (
            "A VPN, internal app, file share, or company-only service is not working."
        ),
        "profile_id": "vpn-issue",
        "support_profile_id": "vpn-issue",
    },
    {
        "id": "device-feels-slow",
        "label": "Device feels slow",
        "description": (
            "The device feels unusually slow, overloaded, or unstable while you work."
        ),
        "profile_id": "device-slow",
        "support_profile_id": "device-slow",
    },
    {
        "id": "something-else",
        "label": "Something else",
        "description": (
            "You need a general local check before deciding what kind of help you need."
        ),
        "profile_id": "custom-profile",
        "support_profile_id": "custom-profile",
    },
)


def list_mode_options() -> list[dict[str, str]]:
    """Return the two top-level experience paths."""

    return [dict(option) for option in MODE_OPTIONS]


def list_symptom_options() -> list[dict[str, str]]:
    """Return the plain-language symptom choices for self-serve mode."""

    return [dict(option) for option in SYMPTOM_OPTIONS]


def normalize_mode(raw_value: str | None) -> str | None:
    """Normalize a mode query or form value."""

    if raw_value in {None, ""}:
        return None
    if raw_value in {SELF_SERVE_MODE, SUPPORT_MODE}:
        return raw_value
    raise ValueError("Unknown experience path.")


def get_mode_option(mode: str | None) -> dict[str, str] | None:
    """Return metadata for a mode identifier."""

    if mode is None:
        return None
    for option in MODE_OPTIONS:
        if option["id"] == mode:
            return dict(option)
    raise ValueError("Unknown experience path.")


def get_symptom_option(symptom_id: str | None) -> dict[str, str] | None:
    """Return metadata for a plain-language symptom identifier."""

    if symptom_id in {None, ""}:
        return None
    for option in SYMPTOM_OPTIONS:
        if option["id"] == symptom_id:
            return dict(option)
    raise ValueError("Unknown symptom choice.")


def resolve_self_serve_profile_id(symptom_id: str | None) -> str | None:
    """Map a self-serve symptom choice to a backing local profile."""

    option = get_symptom_option(symptom_id)
    return option["profile_id"] if option else None


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

    symptom = get_symptom_option(symptom_id)
    if symptom is not None:
        return symptom["support_profile_id"]
    if current_profile_id:
        return current_profile_id
    return "custom-profile"
