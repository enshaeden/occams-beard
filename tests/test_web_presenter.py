"""Tests for mode-aware web presentation helpers."""

from __future__ import annotations

import unittest

from occams_beard.web_presenter import (
    SELF_SERVE_MODE,
    SUPPORT_MODE,
    build_results_view,
    resolve_self_serve_profile_id,
    suggest_support_profile_id,
)
from support import (
    build_default_run_result,
    build_degraded_partial_result,
    build_profile_dns_issue_result,
)


class WebPresenterTests(unittest.TestCase):
    """Validate symptom mapping, result prioritization, and support suggestions."""

    def test_symptom_to_profile_mapping_uses_plain_language_choices(self) -> None:
        self.assertEqual(resolve_self_serve_profile_id("internet-not-working"), "no-internet")
        self.assertEqual(resolve_self_serve_profile_id("apps-sites-not-loading"), "dns-issue")
        self.assertEqual(
            resolve_self_serve_profile_id("vpn-or-company-resource-issue"),
            "vpn-issue",
        )
        self.assertEqual(resolve_self_serve_profile_id("device-feels-slow"), "device-slow")
        self.assertEqual(resolve_self_serve_profile_id("something-else"), "custom-profile")

    def test_support_profile_suggestion_prefers_fault_domain_signal(self) -> None:
        dns_result = build_profile_dns_issue_result()
        partial_result = build_degraded_partial_result()

        self.assertEqual(suggest_support_profile_id(dns_result), "dns-issue")
        self.assertEqual(suggest_support_profile_id(partial_result), "no-internet")

    def test_self_serve_results_default_to_simple_summary_and_hidden_passes(self) -> None:
        result = build_default_run_result()

        view = build_results_view(
            result=result,
            options=result_to_options(result),
            mode=SELF_SERVE_MODE,
            continue_with_support_url="/support",
        )

        self.assertFalse(view["technical_open"])
        self.assertEqual(view["mode_label"], "Check My Device")
        self.assertEqual(view["technical_sections"][0]["passed_count"], 2)
        self.assertEqual(view["technical_sections"][0]["notable_items"], [])
        self.assertEqual(view["continue_with_support_url"], "/support")
        self.assertTrue(view["primary_next_step"])
        self.assertNotIn(view["top_takeaway"], view["what_we_know"])

    def test_support_results_surface_partial_state_and_open_technical_detail(self) -> None:
        result = build_degraded_partial_result()

        view = build_results_view(
            result=result,
            options=result_to_options(result),
            mode=SUPPORT_MODE,
        )

        self.assertTrue(view["technical_open"])
        self.assertEqual(view["status_tone"], "attention")
        self.assertGreater(len(view["warning_notes"]), 0)
        self.assertGreater(len(view["heuristic_findings"]), 0)
        self.assertGreater(len(view["evidence_based_findings"]), 0)
        self.assertEqual(view["bundle_raw_capture_label"], "Raw command capture available")
        self.assertIn("Download the support bundle", view["primary_next_step"])
        self.assertIn("best reviewed with support", view["uncertainty_notes"][1])


def result_to_options(result):
    """Recreate run options from a deterministic fixture result."""

    from occams_beard.profile_catalog import get_profile
    from occams_beard.runner import DiagnosticsRunOptions

    profile = get_profile(result.metadata.profile_id) if result.metadata.profile_id else None
    return DiagnosticsRunOptions(
        selected_checks=list(result.metadata.selected_checks),
        targets=[
            check.target
            for check in result.facts.connectivity.tcp_checks
        ] or [
            check.target for check in result.facts.services.checks
        ],
        dns_hosts=[check.hostname for check in result.facts.dns.checks],
        profile=profile,
        enable_ping=bool(result.facts.connectivity.ping_checks),
        enable_trace=bool(result.facts.connectivity.trace_results),
        capture_raw_commands=bool(result.raw_command_capture),
    )


if __name__ == "__main__":
    unittest.main()
