"""Serialization helpers for machine-readable outputs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from endpoint_diagnostics_lab.models import EndpointDiagnosticResult


def to_json_dict(result: EndpointDiagnosticResult) -> dict[str, Any]:
    """Convert a result model into a JSON-friendly dictionary."""

    return asdict(result)


def to_json_text(result: EndpointDiagnosticResult) -> str:
    """Serialize a result model to pretty-printed JSON."""

    return json.dumps(to_json_dict(result), indent=2, sort_keys=False)


def write_json_file(result: EndpointDiagnosticResult, output_path: str) -> Path:
    """Persist a result model as JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json_text(result) + "\n", encoding="utf-8")
    return path
