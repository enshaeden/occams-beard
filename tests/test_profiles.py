"""Tests for local diagnostics profiles."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import occams_beard.profile_catalog as profile_catalog


class ProfileCatalogTests(unittest.TestCase):
    """Validate built-in profile loading."""

    def test_list_profiles_includes_expected_builtins(self) -> None:
        profiles = profile_catalog.list_profiles()

        self.assertTrue(any(profile.profile_id == "no-internet" for profile in profiles))
        self.assertTrue(any(profile.profile_id == "dns-issue" for profile in profiles))
        self.assertTrue(any(profile.profile_id == "custom-profile" for profile in profiles))

    def test_get_profile_returns_expected_defaults(self) -> None:
        profile = profile_catalog.get_profile("vpn-issue")

        self.assertEqual(profile.issue_category, "VPN issue")
        self.assertIn("services", profile.recommended_checks)
        self.assertEqual(profile.tcp_targets[1].host, "10.0.0.10")

    def test_get_profile_catalog_skips_invalid_optional_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            invalid_path = Path(tempdir) / "broken.toml"
            invalid_path.write_text("id = [\n", encoding="utf-8")

            with patch.dict(os.environ, {"OCCAMS_BEARD_PROFILE_DIR": tempdir}, clear=False):
                catalog = profile_catalog.get_profile_catalog()

        self.assertTrue(any(profile.profile_id == "no-internet" for profile in catalog.profiles))
        self.assertEqual(len(catalog.issues), 1)
        self.assertEqual(catalog.issues[0].source, "env")
        self.assertEqual(catalog.issues[0].path, str(invalid_path))
        self.assertIn("not valid TOML", catalog.issues[0].reason)

    def test_get_profile_catalog_raises_for_invalid_builtins(self) -> None:
        invalid_path = Path("/tmp/broken-built-in.toml")
        with patch(
            "occams_beard.profile_catalog._iter_profile_files",
            return_value=[profile_catalog._ProfileCandidate(source="built_in", path=invalid_path)],
        ):
            with patch(
                "occams_beard.profile_catalog._load_profile_file",
                side_effect=profile_catalog.ProfileValidationError(
                    invalid_path,
                    "Profile file is not valid TOML",
                ),
            ):
                with self.assertRaises(profile_catalog.ProfileValidationError):
                    profile_catalog.get_profile_catalog()


if __name__ == "__main__":
    unittest.main()
