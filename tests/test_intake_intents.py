"""Tests for intent-driven intake translation."""

from __future__ import annotations

import unittest

from occams_beard.intake import resolve_intake_intent, resolve_self_serve_profile_id, suggest_support_profile_id
from support import build_degraded_partial_result, build_profile_dns_issue_result


class IntakeIntentTests(unittest.TestCase):
    """Validate symptom-intent translation and support-profile recommendation."""

    def test_resolve_intake_intent_returns_typed_mapping(self) -> None:
        intent = resolve_intake_intent("apps-sites-not-loading")

        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.intent_id, "app_path_partial_connectivity")
        self.assertEqual(intent.self_serve_profile_id, "dns-issue")
        self.assertEqual(intent.support_profile_id, "internal-service-unreachable")

    def test_resolve_self_serve_profile_id_returns_none_without_selection(self) -> None:
        self.assertIsNone(resolve_self_serve_profile_id(None))
        self.assertIsNone(resolve_self_serve_profile_id(""))

    def test_support_profile_suggestion_prefers_fault_domain_before_intent(self) -> None:
        dns_result = build_profile_dns_issue_result()
        partial_result = build_degraded_partial_result()

        self.assertEqual(
            suggest_support_profile_id(
                dns_result,
                symptom_id="something-else",
            ),
            "dns-issue",
        )
        self.assertEqual(suggest_support_profile_id(partial_result), "no-internet")


if __name__ == "__main__":
    unittest.main()
