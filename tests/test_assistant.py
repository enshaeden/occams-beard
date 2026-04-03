"""Tests for deterministic summary shaping helpers."""

from __future__ import annotations

import unittest

from occams_beard.assistant import build_guided_experience, enrich_findings
from occams_beard.models import DiagnosticProfile, DomainExecution, Finding


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

        guided = build_guided_experience(findings, execution, profile)

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


if __name__ == "__main__":
    unittest.main()
