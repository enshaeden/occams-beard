"""Support-ready bundle export for local diagnostics runs."""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

from occams_beard.models import (
    EndpointDiagnosticResult,
    RedactionLevel,
    SupportBundleFile,
    SupportBundleManifest,
)
from occams_beard.privacy import BundleRedactor
from occams_beard.report import render_report
from occams_beard.schema import SUPPORT_BUNDLE_FORMAT_VERSION
from occams_beard.serializers import to_json_dict
from occams_beard.utils.time import utc_now_iso


def build_support_bundle_contents(
    result: EndpointDiagnosticResult,
    *,
    redaction_level: RedactionLevel = "safe",
    include_raw_command_capture: bool = False,
) -> tuple[dict[str, bytes], SupportBundleManifest]:
    """Build a support bundle as an in-memory file mapping."""

    redactor = BundleRedactor(result, redaction_level)

    result_payload = redactor.redact_data(to_json_dict(result))
    result_json_bytes = (json.dumps(result_payload, indent=2) + "\n").encode("utf-8")

    report_text = render_report(result)
    report_bytes = (redactor.redact_text(report_text) + "\n").encode("utf-8")

    redaction_summary = redactor.summary()
    redaction_report_bytes = _render_redaction_report(redaction_summary).encode("utf-8")

    files: dict[str, bytes] = {
        "result.json": result_json_bytes,
        "report.txt": report_bytes,
        "redaction-report.txt": redaction_report_bytes,
    }

    notes: list[str] = []
    raw_capture_included = include_raw_command_capture and bool(result.raw_command_capture)
    if raw_capture_included:
        raw_payload = redactor.redact_raw_commands(result.raw_command_capture)
        files["raw-commands.json"] = (json.dumps(raw_payload, indent=2) + "\n").encode("utf-8")
    elif include_raw_command_capture:
        notes.append(
            "Raw command capture was requested for the bundle, but the "
            "diagnostics run did not collect it."
        )

    manifest = SupportBundleManifest(
        bundle_format_version=SUPPORT_BUNDLE_FORMAT_VERSION,
        generated_at=utc_now_iso(),
        app_version=result.metadata.version,
        schema_version=result.schema_version,
        redaction_level=redaction_level,
        raw_command_capture_included=raw_capture_included,
        selected_checks=list(result.metadata.selected_checks),
        profile_id=result.metadata.profile_id,
        issue_category=result.metadata.issue_category,
        notes=notes,
    )

    manifest.files = [
        SupportBundleFile(
            path=path,
            sha256=_sha256_bytes(payload),
            size_bytes=len(payload),
        )
        for path, payload in sorted(files.items())
    ]
    manifest.extra = {
        "warning_count": len(result.warnings),
        "finding_count": len(result.findings),
    }

    files["manifest.json"] = (json.dumps(asdict(manifest), indent=2) + "\n").encode("utf-8")
    return files, manifest


def write_support_bundle(
    result: EndpointDiagnosticResult,
    output_path: str,
    *,
    redaction_level: RedactionLevel = "safe",
    include_raw_command_capture: bool = False,
) -> Path:
    """Write a support bundle to a local directory or zip archive."""

    files, _manifest = build_support_bundle_contents(
        result,
        redaction_level=redaction_level,
        include_raw_command_capture=include_raw_command_capture,
    )

    path = Path(output_path)
    if path.suffix.lower() == ".zip":
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative_path, payload in sorted(files.items()):
                archive.writestr(relative_path, payload)
        return path

    path.mkdir(parents=True, exist_ok=True)
    for relative_path, payload in files.items():
        file_path = path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(payload)
    return path


def build_support_bundle_archive(
    result: EndpointDiagnosticResult,
    *,
    redaction_level: RedactionLevel = "safe",
    include_raw_command_capture: bool = False,
) -> bytes:
    """Return an in-memory zip archive for explicit support handoff."""

    files, _manifest = build_support_bundle_contents(
        result,
        redaction_level=redaction_level,
        include_raw_command_capture=include_raw_command_capture,
    )
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path, payload in sorted(files.items()):
            archive.writestr(relative_path, payload)
    return buffer.getvalue()


def support_bundle_response_body(
    result: EndpointDiagnosticResult,
    *,
    redaction_level: RedactionLevel = "safe",
    include_raw_command_capture: bool = False,
) -> bytes:
    """Compatibility wrapper for building a support-bundle download payload."""

    return build_support_bundle_archive(
        result,
        redaction_level=redaction_level,
        include_raw_command_capture=include_raw_command_capture,
    )


def _render_redaction_report(summary) -> str:
    lines = [
        "Occam's Beard Redaction Report",
        "================================",
        f"Level: {summary.level}",
        "",
        "Notes",
    ]
    for note in summary.notes:
        lines.append(f"- {note}")
    lines.extend(["", "Counts"])
    if summary.counts:
        for key, value in sorted(summary.counts.items()):
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- No values were redacted.")
    return "\n".join(lines)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
