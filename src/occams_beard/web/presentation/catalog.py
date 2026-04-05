"""Mode and symptom metadata for the local troubleshooting experience."""

from __future__ import annotations

SELF_SERVE_MODE = "self-serve"
SUPPORT_MODE = "support"

MODE_OPTIONS = (
    {
        "id": SELF_SERVE_MODE,
        "label": "Check My Device",
        "description": (
            "Run a quick diagnostic check and gather more information to share with support."
        ),
        "badge": "Self Service",
    },
    {
        "id": SUPPORT_MODE,
        "label": "Work With Support",
        "description": (
            "Use this when IT support asks for deeper testing, a specific "
            "profile, or a support-ready bundle."
        ),
        "badge": "Advanced mode",
    },
)

SYMPTOM_OPTIONS = (
    {
        "id": "internet-not-working",
        "label": "Internet not working",
        "description": (
            "Websites and online apps are not connecting, or everything looks offline."
        ),
    },
    {
        "id": "apps-sites-not-loading",
        "label": "Apps or sites not loading",
        "description": (
            "Some apps, sites, or sign-in pages stall, fail, or only partly load."
        ),
    },
    {
        "id": "vpn-or-company-resource-issue",
        "label": "VPN or company resource issue",
        "description": (
            "A VPN, internal app, file share, or company-only service is not working."
        ),
    },
    {
        "id": "device-feels-slow",
        "label": "Device feels slow",
        "description": (
            "The device feels unusually slow, overloaded, or unstable while you work."
        ),
    },
    {
        "id": "something-else",
        "label": "Something else",
        "description": (
            "You need a general local check before deciding what kind of help you need."
        ),
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
