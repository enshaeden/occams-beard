"""Typed models for intent clarification and refinement state."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClarificationPrompt:
    """Template-ready clarification prompt for a specific intent."""

    key: str
    prompt: str
    options: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """Deterministic refinement state derived from clarification answers."""

    intent_key: str | None
    status: str
    asked_questions: tuple[ClarificationPrompt, ...]
    answered: tuple[tuple[str, str], ...]
    remaining_question_keys: tuple[str, ...]
    pathway_candidates: tuple[str, ...]
    selected_pathway_key: str | None
    next_domains: tuple[str, ...]
    profile_fallback_id: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class ClarificationResult:
    """Result object returned for initial clarification planning."""

    context: DecisionContext
    questions: tuple[ClarificationPrompt, ...]


@dataclass(frozen=True, slots=True)
class ClarificationAnswerError:
    """Structured invalid-answer information for validation failures."""

    code: str
    message: str
