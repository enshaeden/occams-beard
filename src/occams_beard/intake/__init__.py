"""Intent-driven intake contract package."""

from occams_beard.intake.catalog import get_intake_contract
from occams_beard.intake.contracts import (
    ClarificationQuestion,
    ContractValidationIssue,
    IntakeContract,
    IntakeIntent,
    RefinedAnswerPathway,
    SymptomEntry,
    collect_contract_issues,
    validate_contract,
)

__all__ = [
    "ClarificationQuestion",
    "ContractValidationIssue",
    "IntakeContract",
    "IntakeIntent",
    "RefinedAnswerPathway",
    "SymptomEntry",
    "collect_contract_issues",
    "get_intake_contract",
    "validate_contract",
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
