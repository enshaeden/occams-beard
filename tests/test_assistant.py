"""Tests for deterministic summary shaping helpers."""

from __future__ import annotations

import unittest

from occams_beard.assistant import build_guided_experience, enrich_findings
from occams_beard.intake.models import IntakeContext
from occams_beard.models import DiagnosticProfile, DomainExecution, Finding
from support import build_profile_dns_issue_result


class AssistantTests(unittest.TestCase):
    """Validate guided summary rollups and evidence-noise reduction."""

    def test_guided_experience_keeps_heuristics_out_of_what_we_know(self) -> None:
        findings = enrich_findings(
            [
                Finding(
                    identifier="dns-failure-raw-ip-success",
                    severity="high",
                    title="DNS resolution failed but raw IP connectivity succeeded",
                    summary="The endpoint can reach numeric IPs but cannot resolve hostnames.",
                    evidence=["Numeric IP access worked."],
                    probable_cause="The DNS path is the likeliest failure domain.",
                    fault_domain="dns",
                    confidence=0.92,
                ),
                Finding(
                    identifier="mixed-external-tcp-results",
                    severity="low",
                    title="External reachability is inconsistent across targets",
                    summary="Some public targets worked and some failed.",
                    evidence=["One public target worked.", "One public target failed."],
                    probable_cause="Selective filtering or target-side variance is possible.",
                    fault_domain="internet_edge",
                    confidence=0.64,
                    heuristic=True,
                ),
            ]
        )
        execution = [
            DomainExecution(
                domain="dns",
                label="DNS checks",
                status="passed",
                selected=True,
            ),
            DomainExecution(
                domain="services",
                label="Configured services",
                status="not_run",
                selected=False,
            ),
            DomainExecution(
                domain="connectivity",
                label="Generic connectivity",
                status="partial",
                selected=True,
            ),
        ]
        profile = DiagnosticProfile(
            profile_id="dns-issue",
            name="DNS Issue",
            description="Focused DNS troubleshooting.",
            issue_category="DNS issue",
            recommended_checks=["dns", "connectivity"],
        )

        guided = build_guided_experience(
            findings,
            execution,
            build_profile_dns_issue_result().facts,
            profile,
        )

        self.assertIn(
            "The endpoint can reach a numeric external IP, but hostname lookups are failing.",
            guided.what_we_know,
        )
        self.assertNotIn("Heuristic conclusion:", " ".join(guided.what_we_know))
        self.assertTrue(
            any(
                item.startswith("Heuristic conclusion:")
                for item in guided.likely_happened
            )
        )
        self.assertTrue(
            any("partially collected" in item for item in guided.uncertainty_notes),
        )
        self.assertFalse(
            any("was not collected in this run" in item for item in guided.uncertainty_notes),
        )

    def test_enrich_findings_dedupes_evidence_summary_inputs(self) -> None:
        finding = Finding(
            identifier="healthy-baseline",
            severity="info",
            title="No major diagnostic findings detected",
            summary="No supported rule matched.",
            evidence=[
                (
                    "Deterministic rule evaluation completed without triggering "
                    "supported fault signatures."
                ),
                (
                    "Deterministic rule evaluation completed without triggering "
                    "supported fault signatures."
                ),
            ],
            probable_cause="No major failure domain was identified.",
            fault_domain="healthy",
            confidence=0.8,
        )

        [enriched] = enrich_findings([finding])

        self.assertEqual(
            enriched.evidence_summary,
            (
                "Deterministic rule evaluation completed without triggering "
                "supported fault signatures."
            ),
        )

    def test_guided_experience_suppresses_inconsistent_storage_finding(self) -> None:
        fixture = build_profile_dns_issue_result()
        finding = Finding(
            identifier="critical-disk-space-exhaustion",
            severity="high",
            title="Critical disk-space exhaustion on /System/Volumes/Hardware",
            summary="Available disk space is critically low.",
            evidence=["Filesystem /System/Volumes/Hardware is 4.0% utilized."],
            probable_cause="Local filesystem exhaustion is likely affecting writes.",
            fault_domain="local_host",
            confidence=0.95,
            plain_language="Available disk space is critically low.",
        )

        guided = build_guided_experience([finding], [], fixture.facts, None)

        self.assertEqual(guided.what_we_know, [])
        self.assertEqual(guided.likely_happened, [])
        self.assertIn(
            "Guided summary withheld unsupported or internally inconsistent findings.",
            guided.uncertainty_notes,
        )

    def test_guided_experience_includes_intake_scope_context(self) -> None:
        fixture = build_profile_dns_issue_result()
        findings = enrich_findings(
            [
                Finding(
                    identifier="dns-failure-raw-ip-success",
                    severity="high",
                    title="DNS resolution failed but raw IP connectivity succeeded",
                    summary="The endpoint can reach numeric IPs but cannot resolve hostnames.",
                    evidence=["Numeric IP access worked.", "DNS lookup failed for baseline host."],
                    probable_cause="The DNS path is the likeliest failure domain.",
                    fault_domain="dns",
                    confidence=0.92,
                )
            ]
        )
        intake_context = IntakeContext(
            selected_symptom_key="apps-sites-not-loading",
            selected_symptom_label="Apps or sites not loading",
            resolved_intent_key="partial_access_or_dns",
            clarification_answers=(),
            scope_rationale="pathway_selected",
        )

        guided = build_guided_experience(findings, [], fixture.facts, None, intake_context)

        self.assertTrue(
            guided.what_we_know[0].startswith(
                "Checks were scoped for the reported symptom 'Apps or sites not loading'"
            )
        )
        self.assertIn(
            "Likely explanation: The DNS path is the likeliest failure domain.",
            guided.likely_happened,
        )

    def test_guided_experience_withholds_scope_inconsistent_noncritical_finding(self) -> None:
        fixture = build_profile_dns_issue_result()
        finding = Finding(
            identifier="high-memory-pressure",
            severity="medium",
            title="High memory pressure observed",
            summary="Available memory is low.",
            evidence=["Available memory is below 10%."],
            probable_cause="Local host pressure is likely contributing to symptoms.",
            fault_domain="local_host",
            confidence=0.8,
        )
        intake_context = IntakeContext(
            selected_symptom_key="vpn-or-company-resource-issue",
            selected_symptom_label="VPN or company resource issue",
            resolved_intent_key="vpn_or_private_resource_access",
            clarification_answers=(),
            scope_rationale="intent_default_scope",
        )

        guided = build_guided_experience([finding], [], fixture.facts, None, intake_context)

        self.assertEqual(
            guided.what_we_know,
            [
                (
                    "Checks were scoped for the reported symptom 'VPN or company resource issue' "
                    "(intent=vpn_or_private_resource_access, "
                    "scope_reason=intent_default_scope)."
                )
            ],
        )
        self.assertEqual(guided.likely_happened, [])
        self.assertIn(
            "Guided summary withheld unsupported or internally inconsistent findings.",
            guided.uncertainty_notes,
        )


if __name__ == "__main__":
    unittest.main()
