"""Tests for intent-driven intake contract integrity."""

from __future__ import annotations

import unittest

from occams_beard.intake import collect_contract_issues, get_intake_contract


class IntakeContractTests(unittest.TestCase):
    """Validate canonical intake mapping structure."""

    def test_intent_taxonomy_stays_constrained(self) -> None:
        contract = get_intake_contract()

        self.assertGreaterEqual(len(contract.intents), 6)
        self.assertLessEqual(len(contract.intents), 8)

    def test_contract_has_no_structural_issues(self) -> None:
        contract = get_intake_contract()

        self.assertEqual(collect_contract_issues(contract), ())

    def test_every_symptom_maps_to_known_intent(self) -> None:
        contract = get_intake_contract()
        intent_keys = {intent.key for intent in contract.intents}

        for symptom in contract.symptoms:
            self.assertIn(symptom.intent_key, intent_keys)

    def test_all_intents_have_clarification_and_pathway(self) -> None:
        contract = get_intake_contract()

        for intent in contract.intents:
            self.assertGreaterEqual(len(intent.clarification_keys), 1)
            self.assertGreaterEqual(len(intent.pathway_keys), 1)

    def test_all_pathways_map_to_domains_and_profile_fallback(self) -> None:
        contract = get_intake_contract()

        for pathway in contract.refined_answer_pathways:
            self.assertTrue(pathway.profile_fallback_id)
            self.assertGreaterEqual(len(pathway.next_domains), 1)

    def test_existing_web_symptoms_remain_covered(self) -> None:
        contract = get_intake_contract()

        contract_symptom_keys = {symptom.key for symptom in contract.symptoms}
        legacy_web_keys = {
            "internet-not-working",
            "apps-sites-not-loading",
            "vpn-or-company-resource-issue",
            "device-feels-slow",
            "something-else",
        }
        self.assertTrue(legacy_web_keys.issubset(contract_symptom_keys))


if __name__ == "__main__":
    unittest.main()
