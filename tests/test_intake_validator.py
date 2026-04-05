"""Tests for pre-execution intake scope validation."""

from __future__ import annotations

import unittest

from occams_beard.intake.models import IntakeContext
from occams_beard.intake.validator import validate_intake_selected_checks


class IntakeScopeValidatorTests(unittest.TestCase):
    """Validate deterministic guardrails for self-serve execution scope."""

    def _intake_context(self, *, intent_key: str | None, symptom_key: str) -> IntakeContext:
        return IntakeContext(
            selected_symptom_key=symptom_key,
            selected_symptom_label=symptom_key,
            resolved_intent_key=intent_key,
            clarification_answers=(),
            scope_rationale="intent_default_scope",
        )

    def test_network_symptom_storage_first_scope_is_conservatively_adjusted(self) -> None:
        result = validate_intake_selected_checks(
            ["storage", "network"],
            intake_context=self._intake_context(
                intent_key="internet_connectivity_loss",
                symptom_key="internet-not-working",
            ),
        )

        self.assertEqual(result.decision, "adjusted_conservative")
        self.assertEqual(result.selected_checks, ("network", "routing"))

    def test_battery_issue_like_local_symptom_drops_routing_and_dns_noise(self) -> None:
        result = validate_intake_selected_checks(
            ["routing", "dns", "resources"],
            intake_context=self._intake_context(
                intent_key="local_performance_degradation",
                symptom_key="device-feels-slow",
            ),
        )

        self.assertEqual(result.decision, "adjusted_conservative")
        self.assertEqual(result.selected_checks, ("resources", "host"))
        self.assertNotIn("routing", result.selected_checks)
        self.assertNotIn("dns", result.selected_checks)

    def test_app_instability_scope_stays_on_local_system_signals(self) -> None:
        result = validate_intake_selected_checks(
            ["host", "resources", "storage"],
            intake_context=self._intake_context(
                intent_key="local_performance_degradation",
                symptom_key="device-feels-slow",
            ),
        )

        self.assertEqual(result.decision, "approved")
        self.assertEqual(result.selected_checks, ("host", "resources", "storage"))

    def test_unknown_issue_falls_back_to_safe_broader_baseline(self) -> None:
        result = validate_intake_selected_checks(
            ["storage"],
            intake_context=self._intake_context(intent_key=None, symptom_key="something-else"),
        )

        self.assertEqual(result.decision, "fallback_baseline")
        self.assertEqual(
            result.selected_checks,
            ("host", "network", "routing", "dns", "connectivity", "resources"),
        )


if __name__ == "__main__":
    unittest.main()
