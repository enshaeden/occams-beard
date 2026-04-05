"""Deterministic intake intent resolver.

This module provides the first executable intake layer. It resolves either a
legacy symptom identifier or a free-text phrase into a stable internal intent
key and emits trace metadata to support debugging and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from occams_beard.intake.catalog import get_intake_contract

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class IntakeResolution:
    """Structured interpretation result produced by the intake resolver."""

    primary_intent: str | None
    confidence_score: float
    alternative_intents: tuple[str, ...]
    trace: dict[str, Any]


@dataclass(frozen=True, slots=True)
class _PhraseRule:
    """Internal phrase-level rule used for deterministic matching."""

    intent_key: str
    phrase: str
    normalized_phrase: str
    phrase_tokens: frozenset[str]
    source: str


def resolve_intake_interpretation(user_input: str | None) -> IntakeResolution:
    """Resolve free-text or symptom-id input into an internal intake intent.

    Rule order is deterministic:

    1. Exact symptom id lookup.
    2. Exact phrase match against symptom labels and representative phrases.
    3. Exact phrase match against intent representative phrases.
    4. Token-overlap scoring across all phrase rules.

    Unknown or empty input returns an unresolved interpretation with confidence
    ``0.0``.
    """

    normalized = _normalize(user_input)
    contract = get_intake_contract()
    symptom_by_key = {_normalize(symptom.key): symptom for symptom in contract.symptoms}

    trace: dict[str, Any] = {
        "raw_input": user_input,
        "normalized_input": normalized,
        "input_kind": "empty" if not normalized else "text",
        "match_rule": "none",
        "matched_symptom_id": None,
        "matched_phrase": None,
        "candidate_scores": {},
    }

    if not normalized:
        return IntakeResolution(
            primary_intent=None,
            confidence_score=0.0,
            alternative_intents=(),
            trace=trace,
        )

    if normalized in symptom_by_key:
        symptom = symptom_by_key[normalized]
        trace["input_kind"] = "symptom_id"
        trace["match_rule"] = "exact_symptom_id"
        trace["matched_symptom_id"] = symptom.key
        trace["candidate_scores"] = {symptom.intent_key: 1.0}
        return IntakeResolution(
            primary_intent=symptom.intent_key,
            confidence_score=1.0,
            alternative_intents=(),
            trace=trace,
        )

    rules = _build_phrase_rules()

    exact_matches = [rule for rule in rules if normalized == rule.normalized_phrase]
    if exact_matches:
        candidate_scores = _collect_best_scores(exact_matches, base_score=0.92)
        primary_intent, confidence, alternatives = _pick_resolution(candidate_scores)
        best_rule = exact_matches[0]
        trace["match_rule"] = f"exact_{best_rule.source}_phrase"
        trace["matched_phrase"] = best_rule.phrase
        trace["candidate_scores"] = candidate_scores
        return IntakeResolution(
            primary_intent=primary_intent,
            confidence_score=confidence,
            alternative_intents=alternatives,
            trace=trace,
        )

    token_scores: dict[str, float] = {}
    matched_rules: list[tuple[_PhraseRule, float]] = []
    input_tokens = _tokenize(normalized)
    for rule in rules:
        overlap = input_tokens & rule.phrase_tokens
        ratio = len(overlap) / len(rule.phrase_tokens) if rule.phrase_tokens else 0.0
        if len(overlap) >= 2 and ratio >= 0.8:
            rule_score = 0.78
        elif len(overlap) >= 2 and ratio >= 0.5:
            rule_score = 0.64
        elif len(overlap) >= 1 and ratio >= 0.25:
            rule_score = 0.45
        else:
            continue

        matched_rules.append((rule, rule_score))
        previous = token_scores.get(rule.intent_key, 0.0)
        token_scores[rule.intent_key] = max(previous, rule_score)

    trace["candidate_scores"] = token_scores

    if not token_scores:
        trace["match_rule"] = "unknown"
        return IntakeResolution(
            primary_intent=None,
            confidence_score=0.0,
            alternative_intents=(),
            trace=trace,
        )

    primary_intent, confidence, alternatives = _pick_resolution(token_scores)
    best_rule, best_score = sorted(
        matched_rules,
        key=lambda item: (-item[1], item[0].intent_key, item[0].normalized_phrase),
    )[0]
    trace["match_rule"] = f"token_overlap_{best_rule.source}"
    trace["matched_phrase"] = best_rule.phrase
    trace["matched_rule_score"] = best_score

    return IntakeResolution(
        primary_intent=primary_intent,
        confidence_score=confidence,
        alternative_intents=alternatives,
        trace=trace,
    )


def _collect_best_scores(matches: list[_PhraseRule], *, base_score: float) -> dict[str, float]:
    scores: dict[str, float] = {}
    for rule in matches:
        current = scores.get(rule.intent_key, 0.0)
        scores[rule.intent_key] = max(current, base_score)
    return scores


def _pick_resolution(candidate_scores: dict[str, float]) -> tuple[str, float, tuple[str, ...]]:
    ranked = sorted(candidate_scores.items(), key=lambda item: (-item[1], item[0]))
    primary_intent, top_score = ranked[0]

    near_ties = [
        intent_key
        for intent_key, score in ranked[1:]
        if score >= max(0.0, top_score - 0.05)
    ]
    alternatives = tuple(intent_key for intent_key, _score in ranked[1:4])
    adjusted_confidence = round(max(0.0, top_score - (0.15 if near_ties else 0.0)), 2)
    return primary_intent, adjusted_confidence, alternatives


def _build_phrase_rules() -> tuple[_PhraseRule, ...]:
    contract = get_intake_contract()
    symptom_rules: list[_PhraseRule] = []
    intent_rules: list[_PhraseRule] = []

    for symptom in contract.symptoms:
        symptom_rules.append(
            _PhraseRule(
                intent_key=symptom.intent_key,
                phrase=symptom.label,
                normalized_phrase=_normalize(symptom.label),
                phrase_tokens=_tokenize(symptom.label),
                source="symptom",
            )
        )
        for phrase in symptom.representative_phrases:
            symptom_rules.append(
                _PhraseRule(
                    intent_key=symptom.intent_key,
                    phrase=phrase,
                    normalized_phrase=_normalize(phrase),
                    phrase_tokens=_tokenize(phrase),
                    source="symptom",
                )
            )

    for intent in contract.intents:
        for phrase in intent.representative_phrases:
            intent_rules.append(
                _PhraseRule(
                    intent_key=intent.key,
                    phrase=phrase,
                    normalized_phrase=_normalize(phrase),
                    phrase_tokens=_tokenize(phrase),
                    source="intent",
                )
            )

    return tuple(symptom_rules + intent_rules)


def _normalize(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(_TOKEN_RE.findall(value.lower())).strip()


def _tokenize(value: str) -> frozenset[str]:
    normalized = _normalize(value)
    if not normalized:
        return frozenset()
    return frozenset(normalized.split())
