"""Tests for deterministic intake resolver behavior."""

from __future__ import annotations

import unittest

from occams_beard.intake.resolver import resolve_intake_interpretation


class IntakeResolverTests(unittest.TestCase):
    """Validate rule-based resolution from symptom IDs and free text."""

    def test_exact_symptom_id_maps_to_expected_intent(self) -> None:
        resolution = resolve_intake_interpretation("apps-sites-not-loading")

        self.assertEqual(resolution.primary_intent, "partial_access_or_dns")
        self.assertEqual(resolution.confidence_score, 1.0)
        self.assertEqual(resolution.alternative_intents, ())
        self.assertEqual(resolution.trace["match_rule"], "exact_symptom_id")

    def test_representative_phrase_maps_to_intent(self) -> None:
        resolution = resolve_intake_interpretation("certificate invalid")

        self.assertEqual(resolution.primary_intent, "clock_or_trust_failure")
        self.assertGreaterEqual(resolution.confidence_score, 0.9)
        self.assertEqual(resolution.trace["match_rule"], "exact_intent_phrase")

    def test_ambiguous_text_returns_alternatives(self) -> None:
        resolution = resolve_intake_interpretation("cannot access intranet app")

        self.assertEqual(resolution.primary_intent, "vpn_or_private_resource_access")
        self.assertGreaterEqual(len(resolution.alternative_intents), 1)
        self.assertIn("partial_access_or_dns", resolution.alternative_intents)
        self.assertLessEqual(resolution.confidence_score, 0.78)

    def test_unknown_input_returns_unresolved_result(self) -> None:
        resolution = resolve_intake_interpretation("printer jam in office")

        self.assertIsNone(resolution.primary_intent)
        self.assertEqual(resolution.confidence_score, 0.0)
        self.assertEqual(resolution.alternative_intents, ())
        self.assertEqual(resolution.trace["match_rule"], "unknown")

    def test_confidence_levels_distinguish_exact_and_partial_matches(self) -> None:
        exact = resolve_intake_interpretation("internet-not-working")
        partial = resolve_intake_interpretation("internet down at home")

        self.assertGreater(exact.confidence_score, partial.confidence_score)
        self.assertGreater(partial.confidence_score, 0.0)


if __name__ == "__main__":
    unittest.main()
