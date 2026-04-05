"""Tests for subprocess capture behavior."""

from __future__ import annotations

import unittest

from occams_beard.utils.subprocess import capture_command_output, run_command


class SubprocessUtilsTests(unittest.TestCase):
    """Validate raw-command capture guardrails."""

    def test_run_command_can_skip_bundle_capture_for_sensitive_output(self) -> None:
        with capture_command_output() as captured:
            result = run_command(
                ["python3", "-c", "print('sensitive-process-name')"],
                capture_output_for_bundle=False,
            )

        self.assertTrue(result.succeeded)
        self.assertEqual(result.stdout.strip(), "sensitive-process-name")
        self.assertEqual(captured, [])


if __name__ == "__main__":
    unittest.main()
