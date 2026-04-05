"""Tests for contract-driven clarification planning and refinement."""

from __future__ import annotations

import unittest

from occams_beard.intake import get_intake_contract
from occams_beard.intake.clarification import (
    build_clarification_questions,
    refine_decision_context,
)


class IntakeClarificationTests(unittest.TestCase):
    """Validate deterministic clarification generation and answer refinement."""

    def test_each_intent_generates_minimal_question_set(self) -> None:
        contract = get_intake_contract()

        for intent in contract.intents:
            result = build_clarification_questions(intent.key)
            expected_keys = tuple(intent.clarification_keys[:2])

            self.assertLessEqual(len(result.questions), 2)
            self.assertEqual(tuple(question.key for question in result.questions), expected_keys)
            self.assertEqual(result.context.pathway_candidates, intent.pathway_keys)
            self.assertEqual(result.context.status, "needs_clarification")

    def test_answer_refines_context_to_specific_pathway(self) -> None:
        result = build_clarification_questions("partial_access_or_dns")

        updated, error = refine_decision_context(
            result.context,
            question_key="dns_error_surface",
            answer="dns_or_name_error",
        )

        self.assertIsNone(error)
        self.assertEqual(updated.selected_pathway_key, "resolver_and_routing")
        self.assertIn("dns", updated.next_domains)
        self.assertEqual(updated.profile_fallback_id, "dns-issue")

    def test_invalid_answer_is_rejected_without_mutating_context(self) -> None:
        result = build_clarification_questions("internet_connectivity_loss")

        updated, error = refine_decision_context(
            result.context,
            question_key="scope_of_failure",
            answer="definitely",
        )

        self.assertIsNotNone(error)
        assert error is not None
        self.assertEqual(error.code, "invalid_option")
        self.assertEqual(updated, result.context)

    def test_unresolved_answers_fall_back_to_default_pathway(self) -> None:
        result = build_clarification_questions("support_bundle_preparation")

        updated, error = refine_decision_context(
            result.context,
            question_key="bundle_depth",
            answer="summary_only",
        )

        self.assertIsNone(error)
        self.assertEqual(updated.reason, "fallback_default_pathway")
        self.assertEqual(updated.selected_pathway_key, "support_handoff_path")
        self.assertEqual(updated.status, "ready")

    def test_unknown_intent_returns_unresolved_plan(self) -> None:
        result = build_clarification_questions("not-a-real-intent")

        self.assertEqual(result.questions, ())
        self.assertEqual(result.context.status, "unresolved")
        self.assertEqual(result.context.reason, "unknown_intent")


if __name__ == "__main__":
    unittest.main()
