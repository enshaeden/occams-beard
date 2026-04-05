"""Typed runtime models for preserving intake reasoning context."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IntakeContext:
    """Reasoning context captured during intake and attached to a run."""

    selected_symptom_key: str | None
    selected_symptom_label: str | None
    resolved_intent_key: str | None
    clarification_answers: tuple[tuple[str, str], ...] = ()
    scope_rationale: str = "unspecified"
