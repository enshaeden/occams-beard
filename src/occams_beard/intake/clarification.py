"""Deterministic clarification engine for intent narrowing.

This module is intentionally framework-agnostic so web/forms.py and future route
handlers can consume the same typed outputs without Flask coupling.
"""

from __future__ import annotations

from dataclasses import replace
import re

from occams_beard.intake.catalog import get_intake_contract
from occams_beard.intake.clarification_models import (
    ClarificationAnswerError,
    ClarificationPrompt,
    ClarificationResult,
    DecisionContext,
)
from occams_beard.intake.contracts import (
    ClarificationQuestion,
    IntakeContract,
    IntakeIntent,
    RefinedAnswerPathway,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class ClarificationEngine:
    """Contract-driven engine for clarification planning and refinement."""

    def __init__(self, contract: IntakeContract) -> None:
        self._contract = contract
        self._intent_by_key = {intent.key: intent for intent in contract.intents}
        self._question_by_key = {
            question.key: question for question in contract.clarification_questions
        }
        self._pathway_by_key = {
            pathway.key: pathway for pathway in contract.refined_answer_pathways
        }

    def build_question_set(self, intent_key: str | None) -> ClarificationResult:
        """Return minimal clarification questions and initial decision context."""

        if intent_key is None:
            context = DecisionContext(
                intent_key=None,
                status="unresolved",
                asked_questions=(),
                answered=(),
                remaining_question_keys=(),
                pathway_candidates=(),
                selected_pathway_key=None,
                next_domains=(),
                profile_fallback_id=None,
                reason="missing_intent",
            )
            return ClarificationResult(context=context, questions=())

        intent = self._intent_by_key.get(intent_key)
        if intent is None:
            context = DecisionContext(
                intent_key=intent_key,
                status="unresolved",
                asked_questions=(),
                answered=(),
                remaining_question_keys=(),
                pathway_candidates=(),
                selected_pathway_key=None,
                next_domains=(),
                profile_fallback_id=None,
                reason="unknown_intent",
            )
            return ClarificationResult(context=context, questions=())

        questions = tuple(
            _to_prompt(self._question_by_key[key]) for key in intent.clarification_keys[:2]
        )
        context = DecisionContext(
            intent_key=intent.key,
            status="needs_clarification" if questions else "ready",
            asked_questions=questions,
            answered=(),
            remaining_question_keys=tuple(question.key for question in questions),
            pathway_candidates=intent.pathway_keys,
            selected_pathway_key=None,
            next_domains=(),
            profile_fallback_id=None,
            reason="awaiting_answers" if questions else "no_clarification_required",
        )
        return ClarificationResult(context=context, questions=questions)

    def apply_answer(
        self,
        context: DecisionContext,
        *,
        question_key: str,
        answer: str,
    ) -> tuple[DecisionContext, ClarificationAnswerError | None]:
        """Apply one clarification answer and return an updated context."""

        if context.intent_key is None:
            return context, ClarificationAnswerError(
                code="missing_intent",
                message="Cannot refine context because no intent was resolved.",
            )

        question = self._question_by_key.get(question_key)
        if question is None or question_key not in context.remaining_question_keys:
            return context, ClarificationAnswerError(
                code="unknown_question",
                message="Question is not valid for this clarification context.",
            )

        normalized_answer = _normalize(answer)
        valid_options = {_normalize(option): option for option in question.options}
        canonical_answer = valid_options.get(normalized_answer)
        if canonical_answer is None:
            return context, ClarificationAnswerError(
                code="invalid_option",
                message=f"Answer '{answer}' is not one of the allowed options.",
            )

        scored = _score_pathways(
            answer=canonical_answer,
            pathways=[self._pathway_by_key[key] for key in context.pathway_candidates],
        )
        ranked = sorted(scored.items(), key=lambda item: (-item[1], item[0]))

        remaining = tuple(key for key in context.remaining_question_keys if key != question_key)
        answered = context.answered + ((question_key, canonical_answer),)

        if not ranked or ranked[0][1] <= 0:
            if remaining:
                return (
                    replace(
                        context,
                        answered=answered,
                        remaining_question_keys=remaining,
                        status="needs_clarification",
                        reason="answer_uninformative",
                    ),
                    None,
                )

            default_pathway = context.pathway_candidates[0] if context.pathway_candidates else None
            return (
                self._with_pathway(
                    context,
                    answered=answered,
                    remaining=remaining,
                    pathway_key=default_pathway,
                    reason="fallback_default_pathway",
                ),
                None,
            )

        top_key, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else -1.0
        ambiguous = second_score >= top_score and top_score > 0

        if ambiguous and remaining:
            return (
                replace(
                    context,
                    answered=answered,
                    remaining_question_keys=remaining,
                    status="needs_clarification",
                    reason="ambiguous_answer",
                ),
                None,
            )

        if ambiguous:
            fallback_key = context.pathway_candidates[0] if context.pathway_candidates else top_key
            return (
                self._with_pathway(
                    context,
                    answered=answered,
                    remaining=remaining,
                    pathway_key=fallback_key,
                    reason="ambiguous_fallback",
                ),
                None,
            )

        return (
            self._with_pathway(
                context,
                answered=answered,
                remaining=remaining,
                pathway_key=top_key,
                reason="pathway_selected",
            ),
            None,
        )

    def _with_pathway(
        self,
        context: DecisionContext,
        *,
        answered: tuple[tuple[str, str], ...],
        remaining: tuple[str, ...],
        pathway_key: str | None,
        reason: str,
    ) -> DecisionContext:
        if pathway_key is None:
            return replace(
                context,
                answered=answered,
                remaining_question_keys=remaining,
                status="unresolved",
                reason=reason,
            )

        pathway = self._pathway_by_key[pathway_key]
        return replace(
            context,
            answered=answered,
            remaining_question_keys=remaining,
            selected_pathway_key=pathway.key,
            next_domains=pathway.next_domains,
            profile_fallback_id=pathway.profile_fallback_id,
            status="ready" if not remaining else "needs_clarification",
            reason=reason,
        )


def build_clarification_questions(intent_key: str | None) -> ClarificationResult:
    """Convenience function for generating initial clarification state."""

    return ClarificationEngine(get_intake_contract()).build_question_set(intent_key)


def refine_decision_context(
    context: DecisionContext,
    *,
    question_key: str,
    answer: str,
) -> tuple[DecisionContext, ClarificationAnswerError | None]:
    """Convenience function for applying one clarification answer."""

    return ClarificationEngine(get_intake_contract()).apply_answer(
        context,
        question_key=question_key,
        answer=answer,
    )


def _to_prompt(question: ClarificationQuestion) -> ClarificationPrompt:
    return ClarificationPrompt(
        key=question.key,
        prompt=question.prompt,
        options=question.options,
    )


def _score_pathways(
    *,
    answer: str,
    pathways: list[RefinedAnswerPathway],
) -> dict[str, int]:
    answer_tokens = set(_tokens(answer))
    answer_tokens.update(_derived_answer_hints(answer_tokens))
    scores: dict[str, int] = {}
    for pathway in pathways:
        signal_tokens = set(_tokens(pathway.key))
        signal_tokens.update(_tokens(pathway.label))
        signal_tokens.update(_tokens(pathway.profile_fallback_id))
        for domain in pathway.next_domains:
            signal_tokens.update(_tokens(domain))
        scores[pathway.key] = len(answer_tokens & signal_tokens)
    return scores



def _derived_answer_hints(answer_tokens: set[str]) -> set[str]:
    hints: set[str] = set()
    if {"dns", "name"} & answer_tokens:
        hints.update({"resolver", "routing"})
    if {"certificate", "time", "clock"} & answer_tokens:
        hints.update({"time", "dns"})
    if {"company", "vpn", "private", "resource", "resources"} & answer_tokens:
        hints.update({"vpn", "services"})
    if {"all", "internet"} & answer_tokens:
        hints.update({"network", "connectivity"})
    if {"slow", "load", "intermittent", "always"} & answer_tokens:
        hints.update({"host", "resources"})
    return hints

def _normalize(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(_TOKEN_RE.findall(value.lower())).strip()


def _tokens(value: str | None) -> frozenset[str]:
    normalized = _normalize(value)
    return frozenset(normalized.split()) if normalized else frozenset()
