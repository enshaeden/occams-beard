"""Tests for intent/clarification to execution-domain mapping."""

from __future__ import annotations

import unittest

from occams_beard.defaults import DEFAULT_CHECKS
from occams_beard.intake import (
    get_intake_contract,
    map_intake_to_scope,
    resolve_intake_interpretation,
)
from occams_beard.intake.clarification import build_clarification_questions, refine_decision_context
from occams_beard.intake.clarification_models import DecisionContext


class IntakeDomainMapperTests(unittest.TestCase):
    """Validate self-serve domain selection from intake and clarification."""

    def test_self_serve_symptom_resolves_to_intent_driven_checks(self) -> None:
        resolution = resolve_intake_interpretation("vpn-or-company-resource-issue")

        mapping = map_intake_to_scope(resolution=resolution, contract=get_intake_contract())

        self.assertEqual(
            mapping.selected_checks,
            ("network", "routing", "vpn", "services"),
        )
        self.assertEqual(mapping.suggested_profile_id, "vpn-issue")
        self.assertIsNone(mapping.fallback_mode)

    def test_clarification_context_can_refine_selected_domains(self) -> None:
        resolution = resolve_intake_interpretation("apps-sites-not-loading")
        question_set = build_clarification_questions("partial_access_or_dns")
        refined_context, error = refine_decision_context(
            question_set.context,
            question_key="dns_error_surface",
            answer="dns_or_name_error",
        )

        self.assertIsNone(error)
        mapping = map_intake_to_scope(
            resolution=resolution,
            contract=get_intake_contract(),
            context=refined_context,
        )

        self.assertEqual(mapping.selected_checks, ("dns", "routing", "connectivity"))
        self.assertEqual(mapping.suggested_profile_id, "dns-issue")

    def test_unknown_intent_falls_back_to_general_path(self) -> None:
        resolution = resolve_intake_interpretation(None)

        mapping = map_intake_to_scope(resolution=resolution, contract=get_intake_contract())

        self.assertEqual(mapping.selected_checks, tuple(DEFAULT_CHECKS))
        self.assertEqual(mapping.suggested_profile_id, "custom-profile")
        self.assertEqual(mapping.fallback_mode, "general_triage")

    def test_unknown_refined_domains_fall_back_to_custom_profile_mode(self) -> None:
        resolution = resolve_intake_interpretation("internet-not-working")
        context = DecisionContext(
            intent_key="internet_connectivity_loss",
            status="ready",
            asked_questions=(),
            answered=(),
            remaining_question_keys=(),
            pathway_candidates=(),
            selected_pathway_key=None,
            next_domains=("not-a-real-domain",),
            profile_fallback_id=None,
            reason="test_unknown_domain",
        )

        mapping = map_intake_to_scope(
            resolution=resolution,
            contract=get_intake_contract(),
            context=context,
        )

        self.assertEqual(mapping.selected_checks, tuple(DEFAULT_CHECKS))
        self.assertEqual(mapping.suggested_profile_id, "custom-profile")
        self.assertEqual(mapping.fallback_mode, "custom_profile")


if __name__ == "__main__":
    unittest.main()
