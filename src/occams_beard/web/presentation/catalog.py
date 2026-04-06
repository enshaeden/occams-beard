"""Presentation metadata for top-level local troubleshooting choices.

This module intentionally holds only UI-facing card copy for the browser
experience. Diagnostic scope and symptom-to-intent resolution live in the
intake contract and resolver modules.
"""

from __future__ import annotations

from occams_beard.intake import resolve_self_serve_profile_id, suggest_support_profile_id

SELF_SERVE_MODE = "self-serve"
SUPPORT_MODE = "support"

MODE_OPTIONS = (
    {
        "id": SELF_SERVE_MODE,
        "label": "Check My Device",
        "description": (
            "Use the recommended local check plan when you are troubleshooting "
            "the issue yourself."
        ),
        "badge": "Self Service",
        "action_label": "Start Self-Check",
        "selected_action_label": "Self-Check Selected",
    },
    {
        "id": SUPPORT_MODE,
        "label": "Work With Support",
        "description": (
            "Use the plan support asked you to run when they need a directed "
            "check or a support bundle handoff."
        ),
        "badge": "Support-guided",
        "action_label": "Use Support Path",
        "selected_action_label": "Support Path Selected",
    },
)

SYMPTOM_OPTIONS = (
    {
        "id": "internet-not-working",
        "label": "Internet not working",
        "description": "Websites and online apps do not connect, or the device appears offline.",
    },
    {
        "id": "apps-sites-not-loading",
        "label": "Apps or sites not loading",
        "description": "Some apps, sites, or sign-in pages stall, fail, or load partially.",
    },
    {
        "id": "vpn-or-company-resource-issue",
        "label": "VPN or company resource issue",
        "description": "A VPN, internal app, file share, or company-only service is unavailable.",
    },
    {
        "id": "device-feels-slow",
        "label": "Device feels slow",
        "description": "The device is slow, overloaded, or unstable during normal work.",
    },
    {
        "id": "something-else",
        "label": "Something else / unsure",
        "description": "Run the default diagnostic set when the issue category is not clear.",
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
