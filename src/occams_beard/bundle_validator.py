"""Validation helpers for support-bundle archives and directories."""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Protocol

from occams_beard.schema import SUPPORT_BUNDLE_FORMAT_VERSION


class _BundleReader(Protocol):
    def list_members(self) -> set[str]: ...

    def read_bytes(self, relative_path: str) -> bytes: ...


def validate_support_bundle(bundle_path: str) -> list[str]:
    """Validate a support bundle directory or zip archive."""

    path = Path(bundle_path)
    if not path.exists():
        return [f"Bundle path does not exist: {path}."]
    if path.is_dir():
        return _validate_reader(_DirectoryBundleReader(path))
    if path.is_file() and path.suffix.lower() == ".zip":
        try:
            with zipfile.ZipFile(path, "r") as archive:
                return _validate_reader(_ZipBundleReader(archive))
        except zipfile.BadZipFile:
            return [f"Bundle archive is not a valid zip file: {path}."]
    return [f"Bundle path must be a directory or .zip archive: {path}."]


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for support-bundle validation."""

    parser = argparse.ArgumentParser(
        prog="occams-beard-validate-bundle",
        description="Validate an Occam's Beard support bundle directory or zip archive.",
    )
    parser.add_argument("bundle_path", metavar="PATH", help="Bundle directory or .zip archive.")
    args = parser.parse_args(argv)

    issues = validate_support_bundle(args.bundle_path)
    if issues:
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Support bundle is valid.")
    return 0


class _DirectoryBundleReader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def list_members(self) -> set[str]:
        return {
            str(path.relative_to(self.root))
            for path in self.root.rglob("*")
            if path.is_file()
        }

    def read_bytes(self, relative_path: str) -> bytes:
        return (self.root / relative_path).read_bytes()


class _ZipBundleReader:
    def __init__(self, archive: zipfile.ZipFile) -> None:
        self.archive = archive

    def list_members(self) -> set[str]:
        return {
            name
            for name in self.archive.namelist()
            if name and not name.endswith("/")
        }

    def read_bytes(self, relative_path: str) -> bytes:
        return self.archive.read(relative_path)


def _validate_reader(reader: _BundleReader) -> list[str]:
    issues: list[str] = []
    members = reader.list_members()

    if "manifest.json" not in members:
        return ["Bundle is missing manifest.json."]

    manifest = _load_json(reader, "manifest.json", issues)
    if not isinstance(manifest, dict):
        return issues

    bundle_format_version = manifest.get("bundle_format_version")
    if bundle_format_version != SUPPORT_BUNDLE_FORMAT_VERSION:
        issues.append(
            "Manifest bundle_format_version "
            f"{bundle_format_version!r} does not match supported version "
            f"{SUPPORT_BUNDLE_FORMAT_VERSION!r}."
        )

    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, list):
        issues.append("Manifest files entry is missing or is not a list.")
        return issues

    expected_paths: set[str] = set()
    for index, file_entry in enumerate(manifest_files):
        if not isinstance(file_entry, dict):
            issues.append(f"Manifest file entry {index} is not an object.")
            continue

        relative_path = file_entry.get("path")
        sha256 = file_entry.get("sha256")
        size_bytes = file_entry.get("size_bytes")
        if not isinstance(relative_path, str) or not relative_path:
            issues.append(f"Manifest file entry {index} has an invalid path.")
            continue
        expected_paths.add(relative_path)
        if not isinstance(sha256, str) or not sha256:
            issues.append(f"Manifest file entry {relative_path} has an invalid sha256.")
            continue
        if not isinstance(size_bytes, int) or size_bytes < 0:
            issues.append(f"Manifest file entry {relative_path} has an invalid size_bytes.")
            continue
        if relative_path not in members:
            issues.append(f"Bundle is missing file listed in manifest: {relative_path}.")
            continue

        payload = reader.read_bytes(relative_path)
        if len(payload) != size_bytes:
            issues.append(
                f"File size mismatch for {relative_path}: manifest says {size_bytes}, "
                f"bundle has {len(payload)}."
            )
        if _sha256_bytes(payload) != sha256:
            issues.append(f"SHA-256 mismatch for {relative_path}.")

    unexpected_members = sorted(members - expected_paths - {"manifest.json"})
    if unexpected_members:
        issues.append(
            "Bundle contains unexpected files not listed in manifest: "
            f"{', '.join(unexpected_members)}."
        )

    raw_capture_included = manifest.get("raw_command_capture_included")
    if raw_capture_included is True and "raw-commands.json" not in members:
        issues.append(
            "Manifest says raw command capture is included, "
            "but raw-commands.json is missing."
        )
    if raw_capture_included is False and "raw-commands.json" in members:
        issues.append(
            "Manifest says raw command capture is excluded, but raw-commands.json is present."
        )

    result_payload = _load_json(reader, "result.json", issues)
    if isinstance(result_payload, dict):
        result_schema_version = result_payload.get("schema_version")
        manifest_schema_version = manifest.get("schema_version")
        if result_schema_version != manifest_schema_version:
            issues.append(
                "Schema version mismatch between manifest.json and result.json: "
                f"{manifest_schema_version!r} vs {result_schema_version!r}."
            )

    return issues


def _load_json(reader: _BundleReader, relative_path: str, issues: list[str]) -> object | None:
    try:
        payload = reader.read_bytes(relative_path)
    except FileNotFoundError:
        issues.append(f"Bundle is missing required file: {relative_path}.")
        return None
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        issues.append(f"File is not valid UTF-8 JSON: {relative_path}.")
        return None


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
