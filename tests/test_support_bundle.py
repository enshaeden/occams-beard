"""Tests for support-bundle export and redaction."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile

from occams_beard.models import RawCommandCapture
from occams_beard.privacy import BundleRedactor
from occams_beard.support_bundle import build_support_bundle_contents, write_support_bundle
from support import build_sample_result


class SupportBundleTests(unittest.TestCase):
    """Validate support-bundle structure and redaction behavior."""

    def assert_no_registered_value_leaks(
        self,
        files: dict[str, bytes],
        *,
        result,
        redaction_level: str,
    ) -> None:
        redactor = BundleRedactor(result, redaction_level)
        leaked_values: list[str] = []
        text_files = {
            path: payload.decode("utf-8", errors="replace")
            for path, payload in files.items()
            if path.endswith((".json", ".txt"))
        }
        for value in redactor.registered_values():
            for text in text_files.values():
                if value and value in text:
                    leaked_values.append(value)
                    break
        self.assertEqual(leaked_values, [])

    def test_build_support_bundle_includes_required_files(self) -> None:
        result = build_sample_result()
        result.raw_command_capture = [
            RawCommandCapture(
                command=["ip", "addr", "show"],
                returncode=0,
                stdout="2: eth0 inet 192.168.1.50/24 inet6 fd00::1234/64",
                stderr="gateway demo-host via fd00::1234",
                duration_ms=5,
            )
        ]

        files, manifest = build_support_bundle_contents(
            result,
            redaction_level="safe",
            include_raw_command_capture=True,
        )

        self.assertIn("result.json", files)
        self.assertIn("report.txt", files)
        self.assertIn("manifest.json", files)
        self.assertIn("redaction-report.txt", files)
        self.assertIn("raw-commands.json", files)
        self.assertEqual(manifest.redaction_level, "safe")
        self.assertTrue(manifest.raw_command_capture_included)

        result_payload = json.loads(files["result.json"].decode("utf-8"))
        self.assertEqual(result_payload["schema_version"], "1.1.0")
        self.assertNotEqual(result_payload["facts"]["host"]["hostname"], "demo-host")
        self.assert_no_registered_value_leaks(
            files,
            result=result,
            redaction_level="safe",
        )
        raw_payload = files["raw-commands.json"].decode("utf-8")
        self.assertNotIn("fd00::1234", raw_payload)

    def test_write_support_bundle_zip_creates_local_archive(self) -> None:
        result = build_sample_result()

        with tempfile.TemporaryDirectory() as tempdir:
            bundle_path = write_support_bundle(
                result,
                f"{tempdir}/bundle.zip",
                redaction_level="strict",
            )
            with zipfile.ZipFile(bundle_path, "r") as archive:
                members = sorted(archive.namelist())
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))

        self.assertEqual(
            members,
            ["manifest.json", "redaction-report.txt", "report.txt", "result.json"],
        )
        self.assertEqual(manifest["redaction_level"], "strict")

    def test_support_bundle_redacts_uncatalogued_ipv6_addresses_from_raw_capture(self) -> None:
        result = build_sample_result()
        result.raw_command_capture = [
            RawCommandCapture(
                command=["networksetup", "-getinfo", "Wi-Fi"],
                returncode=0,
                stdout="router: fd00::99 public: 2606:50c0:8003::153",
                stderr="",
                duration_ms=7,
            )
        ]

        files, _manifest = build_support_bundle_contents(
            result,
            redaction_level="strict",
            include_raw_command_capture=True,
        )

        raw_payload = files["raw-commands.json"].decode("utf-8")
        self.assertNotIn("fd00::99", raw_payload)
        self.assertNotIn("2606:50c0:8003::153", raw_payload)


if __name__ == "__main__":
    unittest.main()
