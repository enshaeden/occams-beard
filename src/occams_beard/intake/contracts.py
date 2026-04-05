"""Typed contract structures for intent-driven intake.

This module defines the immutable schema used by the canonical intake catalog.
Runtime wiring is intentionally out of scope for this phase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClarificationQuestion:
    """A question used to narrow an intake intent."""

    key: str
    prompt: str
    options: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RefinedAnswerPathway:
    """A deterministic next-step path after clarification."""

    key: str
    label: str
    profile_fallback_id: str
    next_domains: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IntakeIntent:
    """Internal intent abstraction for intake routing."""

    key: str
    label: str
    description: str
    representative_phrases: tuple[str, ...]
    clarification_keys: tuple[str, ...]
    pathway_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SymptomEntry:
    """User-facing symptom selection mapped to one internal intent."""

    key: str
    label: str
    description: str
    representative_phrases: tuple[str, ...]
    intent_key: str


@dataclass(frozen=True, slots=True)
class IntakeContract:
    """Canonical source of truth for intake mapping and resolution."""

    symptoms: tuple[SymptomEntry, ...]
    intents: tuple[IntakeIntent, ...]
    clarification_questions: tuple[ClarificationQuestion, ...]
    refined_answer_pathways: tuple[RefinedAnswerPathway, ...]


@dataclass(frozen=True, slots=True)
class ContractValidationIssue:
    """Machine-readable contract validation issue."""

    code: str
    message: str


def collect_contract_issues(contract: IntakeContract) -> tuple[ContractValidationIssue, ...]:
    """Return structural validation issues for an intake contract."""

    issues: list[ContractValidationIssue] = []
    if not 6 <= len(contract.intents) <= 8:
        issues.append(
            ContractValidationIssue(
                code="intent_count",
                message="Intent taxonomy must contain between 6 and 8 intents.",
            )
        )

    symptom_keys = [entry.key for entry in contract.symptoms]
    intent_keys = [intent.key for intent in contract.intents]
    question_keys = [question.key for question in contract.clarification_questions]
    pathway_keys = [pathway.key for pathway in contract.refined_answer_pathways]

    for label, keys in (
        ("symptom", symptom_keys),
        ("intent", intent_keys),
        ("clarification question", question_keys),
        ("refined pathway", pathway_keys),
    ):
        duplicates = _find_duplicates(keys)
        for duplicate in duplicates:
            issues.append(
                ContractValidationIssue(
                    code=f"duplicate_{label.replace(' ', '_')}_key",
                    message=f"Duplicate {label} key: {duplicate}",
                )
            )

    intent_key_set = set(intent_keys)
    question_key_set = set(question_keys)
    pathway_key_set = set(pathway_keys)

    for symptom in contract.symptoms:
        if symptom.intent_key not in intent_key_set:
            issues.append(
                ContractValidationIssue(
                    code="unknown_intent_for_symptom",
                    message=(
                        f"Symptom '{symptom.key}' references unknown intent "
                        f"'{symptom.intent_key}'."
                    ),
                )
            )

    for intent in contract.intents:
        if not intent.representative_phrases:
            issues.append(
                ContractValidationIssue(
                    code="empty_intent_phrases",
                    message=f"Intent '{intent.key}' has no representative phrases.",
                )
            )

        for question_key in intent.clarification_keys:
            if question_key not in question_key_set:
                issues.append(
                    ContractValidationIssue(
                        code="unknown_clarification_key",
                        message=(
                            f"Intent '{intent.key}' references unknown clarification "
                            f"question '{question_key}'."
                        ),
                    )
                )

        for pathway_key in intent.pathway_keys:
            if pathway_key not in pathway_key_set:
                issues.append(
                    ContractValidationIssue(
                        code="unknown_pathway_key",
                        message=(
                            f"Intent '{intent.key}' references unknown pathway "
                            f"'{pathway_key}'."
                        ),
                    )
                )

    for pathway in contract.refined_answer_pathways:
        if not pathway.next_domains:
            issues.append(
                ContractValidationIssue(
                    code="empty_domain_mapping",
                    message=f"Pathway '{pathway.key}' must map to at least one domain.",
                )
            )

    return tuple(issues)


def validate_contract(contract: IntakeContract) -> None:
    """Raise ``ValueError`` when contract structure is invalid."""

    issues = collect_contract_issues(contract)
    if issues:
        combined = "; ".join(issue.message for issue in issues)
        raise ValueError(f"Invalid intake contract: {combined}")


def _find_duplicates(values: list[str]) -> set[str]:
    """Return duplicate values preserving no order guarantees."""

    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates
