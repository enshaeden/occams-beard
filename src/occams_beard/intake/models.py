"""Typed runtime models for preserving intake reasoning context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class IntakeContext:
    """Reasoning context captured during intake and attached to a run."""

    selected_symptom_key: str | None
    selected_symptom_label: str | None
    resolved_intent_key: str | None
    clarification_answers: tuple[tuple[str, str], ...] = ()
    scope_rationale: str = "unspecified"
    trace_metadata: dict[str, Any] = field(default_factory=dict)
