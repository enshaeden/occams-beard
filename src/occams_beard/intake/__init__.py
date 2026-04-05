"""Intake translation surface used by web and other entry points."""

from occams_beard.intake.intents import (
    IntakeIntent,
    resolve_intake_intent,
    resolve_self_serve_profile_id,
    suggest_support_profile_id,
)

__all__ = [
    "IntakeIntent",
    "resolve_intake_intent",
    "resolve_self_serve_profile_id",
    "suggest_support_profile_id",
]
