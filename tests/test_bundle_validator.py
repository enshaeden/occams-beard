"""Tests for standalone support-bundle validation."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from occams_beard.bundle_validator import validate_support_bundle
from occams_beard.support_bundle import write_support_bundle
from support import build_sample_result


class BundleValidatorTests(unittest.TestCase):
    """Validate support-bundle verifier behavior."""

    def test_validate_support_bundle_accepts_directory_output(self) -> None:
        result = build_sample_result()

        with tempfile.TemporaryDirectory() as tempdir:
            output_path = write_support_bundle(result, f"{tempdir}/bundle")
            issues = validate_support_bundle(str(output_path))

        self.assertEqual(issues, [])

    def test_validate_support_bundle_accepts_zip_output(self) -> None:
        result = build_sample_result()

        with tempfile.TemporaryDirectory() as tempdir:
            output_path = write_support_bundle(result, f"{tempdir}/bundle.zip")
            issues = validate_support_bundle(str(output_path))

        self.assertEqual(issues, [])

    def test_validate_support_bundle_rejects_manifest_hash_mismatch(self) -> None:
        result = build_sample_result()

        with tempfile.TemporaryDirectory() as tempdir:
            bundle_root = f"{tempdir}/bundle"
            write_support_bundle(result, bundle_root)
            manifest_path = Path(bundle_root) / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][0]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

            issues = validate_support_bundle(bundle_root)

        self.assertTrue(any("SHA-256 mismatch" in issue for issue in issues))

    def test_validate_support_bundle_rejects_schema_mismatch(self) -> None:
        result = build_sample_result()

        with tempfile.TemporaryDirectory() as tempdir:
            bundle_path = write_support_bundle(result, f"{tempdir}/bundle.zip")
            rewritten_members: dict[str, bytes] = {}
            with zipfile.ZipFile(bundle_path, "r") as archive:
                for name in archive.namelist():
                    rewritten_members[name] = archive.read(name)
            payload = json.loads(rewritten_members["result.json"].decode("utf-8"))
            payload["schema_version"] = "9.9.9"
            rewritten_members["result.json"] = (json.dumps(payload, indent=2) + "\n").encode(
                "utf-8"
            )
            with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, content in rewritten_members.items():
                    archive.writestr(name, content)

            issues = validate_support_bundle(str(bundle_path))

        self.assertTrue(any("Schema version mismatch" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
