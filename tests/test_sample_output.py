"""Golden-style validation for committed sample artifacts."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from occams_beard.report import render_report
from occams_beard.serializers import to_json_dict
from occams_beard.support_bundle import build_support_bundle_contents
from support import (
    build_default_run_result,
    build_degraded_partial_result,
    build_profile_dns_issue_result,
    build_profile_vpn_issue_result,
)

SAMPLE_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "sample_output"


class SampleOutputTests(unittest.TestCase):
    """Validate committed sample artifacts against the current code."""

    def test_default_run_sample_matches_current_renderers(self) -> None:
        self._assert_report_and_json(
            sample_dir="default-run",
            result=build_default_run_result(),
        )

    def test_profile_dns_issue_sample_matches_current_renderers(self) -> None:
        self._assert_report_and_json(
            sample_dir="profile-dns-issue",
            result=build_profile_dns_issue_result(),
        )

    def test_degraded_partial_sample_matches_current_renderers(self) -> None:
        self._assert_report_and_json(
            sample_dir="degraded-partial",
            result=build_degraded_partial_result(),
        )

    def test_profile_vpn_issue_sample_matches_current_renderers(self) -> None:
        self._assert_report_and_json(
            sample_dir="profile-vpn-issue",
            result=build_profile_vpn_issue_result(),
        )

    def test_support_bundle_sample_matches_current_bundle_contents(self) -> None:
        with patch(
            "occams_beard.support_bundle.utc_now_iso",
            return_value="2026-04-01T00:15:00+00:00",
        ):
            files, _manifest = build_support_bundle_contents(
                build_degraded_partial_result(),
                redaction_level="safe",
                include_raw_command_capture=False,
            )

        sample_bundle_dir = SAMPLE_OUTPUT_DIR / "support-bundle-safe"
        committed_members = sorted(
            path.name for path in sample_bundle_dir.iterdir() if path.is_file()
        )
        self.assertEqual(committed_members, sorted(files))
        self.assertNotIn("raw-commands.json", files)

        for relative_path, payload in files.items():
            committed_payload = (sample_bundle_dir / relative_path).read_bytes()
            self.assertEqual(
                committed_payload,
                payload,
                msg=f"Sample bundle member drifted: {relative_path}",
            )

    def _assert_report_and_json(self, *, sample_dir: str, result) -> None:
        scenario_dir = SAMPLE_OUTPUT_DIR / sample_dir
        committed_json = json.loads((scenario_dir / "result.json").read_text(encoding="utf-8"))
        committed_report = (scenario_dir / "report.txt").read_text(encoding="utf-8")

        self.assertEqual(committed_json, to_json_dict(result))
        self.assertEqual(committed_report, render_report(result) + "\n")


if __name__ == "__main__":
    unittest.main()
