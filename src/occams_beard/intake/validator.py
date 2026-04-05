"""Deterministic sanity validation for intake-derived self-serve scope."""

from __future__ import annotations

from dataclasses import dataclass

from occams_beard.defaults import DEFAULT_CHECKS
from occams_beard.intake.models import IntakeContext

_CANONICAL_ORDER = tuple(DEFAULT_CHECKS)


@dataclass(frozen=True, slots=True)
class IntakeScopeValidationResult:
    """Validated check scope plus a compact decision rationale."""

    selected_checks: tuple[str, ...]
    decision: str
    rationale: str


@dataclass(frozen=True, slots=True)
class _IntentValidationPolicy:
    allowed_checks: tuple[str, ...]
    baseline_checks: tuple[str, ...]
    required_focus: tuple[str, ...]
    minimum_checks: int


_INTENT_POLICIES: dict[str, _IntentValidationPolicy] = {
    "internet_connectivity_loss": _IntentValidationPolicy(
        allowed_checks=("network", "routing", "dns", "connectivity", "services"),
        baseline_checks=("network", "routing", "dns", "connectivity"),
        required_focus=("network",),
        minimum_checks=2,
    ),
    "partial_access_or_dns": _IntentValidationPolicy(
        allowed_checks=("network", "routing", "dns", "connectivity", "services"),
        baseline_checks=("dns", "routing", "connectivity", "services"),
        required_focus=("dns", "routing"),
        minimum_checks=2,
    ),
    "vpn_or_private_resource_access": _IntentValidationPolicy(
        allowed_checks=("network", "routing", "vpn", "services", "dns", "connectivity"),
        baseline_checks=("network", "routing", "vpn", "services", "dns"),
        required_focus=("vpn", "routing"),
        minimum_checks=3,
    ),
    "local_performance_degradation": _IntentValidationPolicy(
        allowed_checks=("host", "resources", "storage", "time", "services"),
        baseline_checks=("host", "resources", "storage"),
        required_focus=("resources", "storage"),
        minimum_checks=2,
    ),
    "clock_or_trust_failure": _IntentValidationPolicy(
        allowed_checks=("time", "dns", "connectivity", "network"),
        baseline_checks=("time", "dns", "connectivity", "network"),
        required_focus=("time",),
        minimum_checks=2,
    ),
    "support_bundle_preparation": _IntentValidationPolicy(
        allowed_checks=("host", "network", "routing", "dns", "connectivity", "services"),
        baseline_checks=("host", "network", "routing", "dns", "connectivity", "services"),
        required_focus=("host",),
        minimum_checks=3,
    ),
    "general_triage": _IntentValidationPolicy(
        allowed_checks=("host", "network", "routing", "dns", "connectivity", "resources"),
        baseline_checks=("host", "network", "routing", "dns", "connectivity", "resources"),
        required_focus=("host",),
        minimum_checks=3,
    ),
}

_SAFE_BASELINE_CHECKS = ("host", "network", "routing", "dns", "connectivity", "resources")


def validate_intake_selected_checks(
    selected_checks: list[str],
    *,
    intake_context: IntakeContext | None,
) -> IntakeScopeValidationResult:
    """Validate self-serve selected checks against intake intent policy."""

    normalized_selected = _ordered_known_checks(selected_checks)

    if intake_context is None:
        return IntakeScopeValidationResult(
            selected_checks=tuple(normalized_selected),
            decision="not_applicable",
            rationale="no_intake_context",
        )

    intent_key = intake_context.resolved_intent_key
    policy = _INTENT_POLICIES.get(intent_key or "")
    if policy is None:
        return IntakeScopeValidationResult(
            selected_checks=_SAFE_BASELINE_CHECKS,
            decision="fallback_baseline",
            rationale="unknown_intent_safe_baseline",
        )

    allowed = set(policy.allowed_checks)
    filtered = [check for check in normalized_selected if check in allowed]

    has_focus = any(check in set(policy.required_focus) for check in filtered)
    has_only_allowed = len(filtered) == len(normalized_selected)

    if filtered and has_only_allowed and has_focus and len(filtered) >= policy.minimum_checks:
        return IntakeScopeValidationResult(
            selected_checks=tuple(filtered),
            decision="approved",
            rationale="intent_scope_coherent",
        )

    if filtered:
        conservative = _expand_to_minimum(
            selected_checks=tuple(filtered),
            baseline_checks=policy.baseline_checks,
            minimum_checks=policy.minimum_checks,
        )
        return IntakeScopeValidationResult(
            selected_checks=conservative,
            decision="adjusted_conservative",
            rationale="intent_scope_adjusted_to_policy",
        )

    return IntakeScopeValidationResult(
        selected_checks=policy.baseline_checks,
        decision="fallback_baseline",
        rationale="intent_scope_fell_back_to_baseline",
    )


def _ordered_known_checks(checks: list[str]) -> list[str]:
    seen: set[str] = set()
    filtered: list[str] = []
    for canonical in _CANONICAL_ORDER:
        if canonical in checks and canonical not in seen:
            filtered.append(canonical)
            seen.add(canonical)
    return filtered


def _expand_to_minimum(
    *,
    selected_checks: tuple[str, ...],
    baseline_checks: tuple[str, ...],
    minimum_checks: int,
) -> tuple[str, ...]:
    selected_set = set(selected_checks)
    merged: list[str] = [check for check in baseline_checks if check in selected_set]
    for baseline_check in baseline_checks:
        if len(merged) >= minimum_checks:
            break
        if baseline_check not in merged:
            merged.append(baseline_check)
    return tuple(merged)
