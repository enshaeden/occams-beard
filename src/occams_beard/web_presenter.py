"""Compatibility facade for local web presentation helpers."""

from __future__ import annotations

from occams_beard.web.presentation.catalog import (
    SELF_SERVE_MODE,
    SUPPORT_MODE,
    get_mode_option,
    get_symptom_option,
    list_mode_options,
    list_symptom_options,
    normalize_mode,
    resolve_self_serve_profile_id,
    suggest_support_profile_id,
)
from occams_beard.web.presentation.plans import build_collection_plan
from occams_beard.web.presentation.results import build_results_view

__all__ = [
    "SELF_SERVE_MODE",
    "SUPPORT_MODE",
    "build_collection_plan",
    "build_results_view",
    "get_mode_option",
    "get_symptom_option",
    "list_mode_options",
    "list_symptom_options",
    "normalize_mode",
    "resolve_self_serve_profile_id",
    "suggest_support_profile_id",
]
