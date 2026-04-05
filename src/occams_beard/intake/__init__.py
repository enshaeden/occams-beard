"""Intake package surface for contract and deterministic resolver APIs."""

from occams_beard.intake.catalog import get_intake_contract
from occams_beard.intake.clarification import (
    ClarificationEngine,
    build_clarification_questions,
    refine_decision_context,
)
from occams_beard.intake.clarification_models import (
    ClarificationAnswerError,
    ClarificationPrompt,
    ClarificationResult,
    DecisionContext,
)
from occams_beard.intake.contracts import (
    ClarificationQuestion,
    ContractValidationIssue,
    IntakeContract,
    IntakeIntent as ContractIntakeIntent,
    RefinedAnswerPathway,
    SymptomEntry,
    collect_contract_issues,
    validate_contract,
)
from occams_beard.intake.intents import (
    IntakeIntent,
    resolve_intake_intent,
    resolve_self_serve_profile_id,
    suggest_support_profile_id,
)
from occams_beard.intake.resolver import IntakeResolution, resolve_intake_interpretation

__all__ = [
    "ClarificationAnswerError",
    "ClarificationEngine",
    "ClarificationPrompt",
    "ClarificationResult",
    "DecisionContext",
    "ClarificationQuestion",
    "ContractIntakeIntent",
    "ContractValidationIssue",
    "IntakeContract",
    "IntakeIntent",
    "IntakeResolution",
    "RefinedAnswerPathway",
    "SymptomEntry",
    "build_clarification_questions",
    "collect_contract_issues",
    "get_intake_contract",
    "resolve_intake_intent",
    "resolve_intake_interpretation",
    "refine_decision_context",
    "resolve_self_serve_profile_id",
    "suggest_support_profile_id",
    "validate_contract",
]
