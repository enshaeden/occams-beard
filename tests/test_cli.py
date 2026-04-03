"""Tests for the operator-facing CLI."""

from __future__ import annotations

import argparse
import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from occams_beard import cli
from occams_beard.runner import DiagnosticsRunOptions
from support import build_sample_result


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
                "--profile",
                "no-internet",
                "--list-profiles",
                "--support-bundle",
                "bundle.zip",
                "--redaction-level",
                "strict",
                "--bundle-include-raw",
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
        self.assertEqual(args.profile, "no-internet")
        self.assertTrue(args.list_profiles)
        self.assertEqual(args.support_bundle, "bundle.zip")
        self.assertEqual(args.redaction_level, "strict")
        self.assertTrue(args.bundle_include_raw)
        self.assertTrue(args.enable_ping)
        self.assertTrue(args.enable_trace)
        self.assertTrue(args.verbose)
        self.assertTrue(args.debug)

    def test_main_passes_default_run_arguments_to_handler(self) -> None:
        with patch("occams_beard.cli._run_command", return_value=0) as mock_run_command:
            result = cli.main(["run"])

        self.assertEqual(result, 0)
        args = mock_run_command.call_args.args[0]
        self.assertEqual(args.command, "run")
        self.assertIsNone(args.checks)
        self.assertEqual(args.target, [])
        self.assertIsNone(args.target_file)
        self.assertEqual(args.dns_host, [])
        self.assertIsNone(args.profile)
        self.assertFalse(args.list_profiles)
        self.assertIsNone(args.support_bundle)
        self.assertEqual(args.redaction_level, "safe")
        self.assertFalse(args.bundle_include_raw)
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
        with patch("occams_beard.cli._run_command", side_effect=RuntimeError("boom")):
            with self.assertLogs("occams_beard.cli", level="ERROR") as captured:
                result = cli.main(["run"])

        self.assertEqual(result, 1)
        self.assertIn("Diagnostics execution failed: boom", captured.output[0])

    def test_run_command_lists_profiles_without_running_diagnostics(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        args = argparse.Namespace(
            command="run",
            checks=None,
            json_out=None,
            support_bundle=None,
            redaction_level="safe",
            bundle_include_raw=False,
            suppress_report=False,
            target=[],
            target_file=None,
            dns_host=[],
            profile=None,
            list_profiles=True,
            enable_ping=False,
            enable_trace=False,
            verbose=False,
            debug=False,
        )

        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = cli._run_command(args)

        self.assertEqual(result, 0)
        self.assertIn("no-internet", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_run_command_lists_profiles_and_surfaces_skipped_local_files(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        args = argparse.Namespace(
            command="run",
            checks=None,
            json_out=None,
            support_bundle=None,
            redaction_level="safe",
            bundle_include_raw=False,
            suppress_report=False,
            target=[],
            target_file=None,
            dns_host=[],
            profile=None,
            list_profiles=True,
            enable_ping=False,
            enable_trace=False,
            verbose=False,
            debug=False,
        )

        with tempfile.TemporaryDirectory() as tempdir:
            broken_profile = os.path.join(tempdir, "broken.toml")
            with open(broken_profile, "w", encoding="utf-8") as handle:
                handle.write("id = [\n")

            with (
                patch.dict(os.environ, {"OCCAMS_BEARD_PROFILE_DIR": tempdir}, clear=False),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                result = cli._run_command(args)

        self.assertEqual(result, 0)
        self.assertIn("no-internet", stdout.getvalue())
        self.assertIn("Skipped env profile file", stderr.getvalue())
        self.assertIn(broken_profile, stderr.getvalue())

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
        options = DiagnosticsRunOptions(
            selected_checks=["dns"],
            targets=[],
            dns_hosts=["github.com"],
        )
        result_with_findings = build_sample_result()

        with (
            patch("occams_beard.cli.build_run_options", return_value=options),
            patch(
                "occams_beard.cli.run_diagnostics",
                return_value=result_with_findings,
            ),
            patch(
                "occams_beard.cli.render_report",
                return_value="report",
            ),
            patch("builtins.print"),
        ):
            result = cli._run_command(args)

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
