#!/usr/bin/env python3
"""Regenerate canonical sample output artifacts from deterministic fixtures."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(REPO_ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "tests"))


OUTPUT_ROOT = REPO_ROOT / "sample_output"
LEGACY_ARTIFACTS = (
    "healthy-endpoint.json",
    "healthy-endpoint.txt",
    "dns-failure.json",
    "dns-failure.txt",
    "no-default-route.json",
    "no-default-route.txt",
    "high-resource-pressure.json",
    "high-resource-pressure.txt",
    "vpn-private-target-failure.json",
    "vpn-private-target-failure.txt",
)


def main() -> int:
    from occams_beard.report import render_report
    from occams_beard.serializers import to_json_dict
    from occams_beard.support_bundle import build_support_bundle_contents
    from support import (
        build_default_run_result,
        build_degraded_partial_result,
        build_profile_dns_issue_result,
    )

    for name in LEGACY_ARTIFACTS:
        legacy_path = OUTPUT_ROOT / name
        if legacy_path.exists():
            legacy_path.unlink()

    for directory_name, result in (
        ("default-run", build_default_run_result()),
        ("profile-dns-issue", build_profile_dns_issue_result()),
        ("degraded-partial", build_degraded_partial_result()),
    ):
        scenario_root = OUTPUT_ROOT / directory_name
        _reset_directory(scenario_root)
        _write_text(
            scenario_root / "result.json",
            json.dumps(to_json_dict(result), indent=2) + "\n",
        )
        _write_text(scenario_root / "report.txt", render_report(result) + "\n")

    support_bundle_root = OUTPUT_ROOT / "support-bundle-safe"
    _reset_directory(support_bundle_root)
    with patch(
        "occams_beard.support_bundle.utc_now_iso",
        return_value="2026-04-01T00:15:00+00:00",
    ):
        files, _manifest = build_support_bundle_contents(
            build_degraded_partial_result(),
            redaction_level="safe",
            include_raw_command_capture=False,
        )

    for relative_path, payload in sorted(files.items()):
        target_path = support_bundle_root / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(payload)

    return 0


def _reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
