"""Tests for the operator-facing CLI."""

from __future__ import annotations

import argparse
import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from endpoint_diagnostics_lab import cli
from endpoint_diagnostics_lab.models import DnsState, Finding, HostBasics


class CliTests(unittest.TestCase):
    """Validate run-first CLI behavior and exit semantics."""

    def test_build_parser_accepts_run_flags(self) -> None:
        parser = cli.build_parser()

        args = parser.parse_args(
            [
                "run",
                "--checks",
                "dns,connectivity",
                "--json-out",
                "report.json",
                "--suppress-report",
                "--target",
                "github.com:443",
                "--target",
                "1.1.1.1:53",
                "--target-file",
                "targets.json",
                "--dns-host",
                "github.com",
                "--dns-host",
                "python.org",
                "--enable-ping",
                "--enable-trace",
                "--verbose",
                "--debug",
            ]
        )

        self.assertEqual(args.command, "run")
        self.assertEqual(args.checks, "dns,connectivity")
        self.assertEqual(args.json_out, "report.json")
        self.assertTrue(args.suppress_report)
        self.assertEqual(args.target, ["github.com:443", "1.1.1.1:53"])
        self.assertEqual(args.target_file, "targets.json")
        self.assertEqual(args.dns_host, ["github.com", "python.org"])
        self.assertTrue(args.enable_ping)
        self.assertTrue(args.enable_trace)
        self.assertTrue(args.verbose)
        self.assertTrue(args.debug)

    def test_main_passes_default_run_arguments_to_handler(self) -> None:
        with patch("endpoint_diagnostics_lab.cli._run_command", return_value=0) as mock_run_command:
            result = cli.main(["run"])

        self.assertEqual(result, 0)
        args = mock_run_command.call_args.args[0]
        self.assertEqual(args.command, "run")
        self.assertIsNone(args.checks)
        self.assertEqual(args.target, [])
        self.assertIsNone(args.target_file)
        self.assertEqual(args.dns_host, [])
        self.assertFalse(args.enable_ping)
        self.assertFalse(args.enable_trace)
        self.assertFalse(args.suppress_report)
        self.assertFalse(args.verbose)
        self.assertFalse(args.debug)

    def test_main_returns_parser_error_for_invalid_checks(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as context:
                cli.main(["run", "--checks", "dns,invalid"])

        self.assertEqual(context.exception.code, 2)
        self.assertIn("Unsupported diagnostic domains requested: invalid", stderr.getvalue())
        self.assertIn("Supported values:", stderr.getvalue())

    def test_main_returns_non_zero_when_execution_fails(self) -> None:
        with patch("endpoint_diagnostics_lab.cli._run_command", side_effect=RuntimeError("boom")):
            with self.assertLogs("endpoint_diagnostics_lab.cli", level="ERROR") as captured:
                result = cli.main(["run"])

        self.assertEqual(result, 1)
        self.assertIn("Diagnostics execution failed: boom", captured.output[0])

    def test_run_command_returns_zero_when_findings_are_present(self) -> None:
        args = argparse.Namespace(
            command="run",
            checks="dns",
            json_out=None,
            suppress_report=False,
            target=[],
            target_file=None,
            dns_host=[],
            enable_ping=False,
            enable_trace=False,
            verbose=False,
            debug=False,
        )
        finding = Finding(
            identifier="dns-degraded",
            severity="medium",
            title="DNS is degraded",
            summary="At least one hostname failed to resolve.",
            evidence=["github.com failed to resolve."],
            probable_cause="DNS resolution is partially failing.",
            fault_domain="dns",
            confidence=0.88,
        )

        with patch(
            "endpoint_diagnostics_lab.cli.collect_host_basics",
            return_value=(
                HostBasics(
                    hostname="demo-host",
                    operating_system="Linux",
                    kernel="6.8.0",
                    current_user="operator",
                    uptime_seconds=60,
                ),
                [],
            ),
        ), patch(
            "endpoint_diagnostics_lab.cli.collect_dns_state",
            return_value=(DnsState(), []),
        ), patch(
            "endpoint_diagnostics_lab.cli.evaluate_selected_findings",
            return_value=([finding], "dns"),
        ), patch(
            "endpoint_diagnostics_lab.cli.render_report",
            return_value="report",
        ), patch("builtins.print"):
            result = cli._run_command(args)

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
