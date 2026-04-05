"""Form parsing and route-state helpers for the local web interface."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, cast

from flask import request, url_for

from occams_beard.defaults import DEFAULT_DNS_HOSTS, DEFAULT_TCP_TARGETS
from occams_beard.models import (
    DiagnosticProfile,
    EndpointDiagnosticResult,
    RedactionLevel,
    TcpTarget,
)
from occams_beard.profile_catalog import ProfileCatalogIssue, get_profile, get_profile_catalog
from occams_beard.intake import resolve_self_serve_profile_id, suggest_support_profile_id
from occams_beard.web.presentation.catalog import (
    SELF_SERVE_MODE,
    SUPPORT_MODE,
    get_mode_option,
    get_symptom_option,
    normalize_mode,
)
from occams_beard.web.presentation.plans import build_collection_plan
from occams_beard.web.sessions import RunSession, get_store


def page_title(mode: str | None) -> str:
    """Return the current page title for the selected top-level path."""

    if mode == SELF_SERVE_MODE:
        return "Check My Device"
    if mode == SUPPORT_MODE:
        return "Work With Support"
    return "Choose a Check Path"


def query_form_state() -> dict[str, object]:
    """Build a template-ready form state from query parameters."""

    mode = normalize_mode(request.args.get("mode"))
    if mode is None:
        return default_form_state()

    source_record = query_previous_record()
    mode_option = get_mode_option(mode)
    if mode_option is None:
        raise ValueError("Unknown experience path.")

    if mode == SELF_SERVE_MODE:
        symptom = get_symptom_option(request.args.get("symptom"))
        profile = self_serve_profile(symptom["id"] if symptom else None)
    else:
        symptom = None
        profile = get_profile(
            request.args.get("profile") or default_support_profile_id(source_record)
        )

    checks_csv = request.args.get("checks")
    selected_checks = (
        [item for item in checks_csv.split(",") if item]
        if checks_csv
        else list(profile.recommended_checks if profile is not None else [])
    )
    targets_text = request.args.get("targets")
    dns_hosts_text = request.args.get("dns_hosts")
    effective_targets = (
        split_multiline_entries(targets_text)
        if targets_text is not None
        else default_target_lines(profile)
    )
    effective_dns_hosts = (
        split_multiline_entries(dns_hosts_text)
        if dns_hosts_text is not None
        else default_dns_lines(profile)
    )

    return build_form_state(
        mode=mode,
        mode_option=mode_option,
        selected_symptom=symptom,
        selected_profile=profile,
        selected_checks=selected_checks,
        targets_text=targets_text if targets_text is not None else "\n".join(effective_targets),
        dns_hosts_text=(
            dns_hosts_text if dns_hosts_text is not None else "\n".join(effective_dns_hosts)
        ),
        enable_ping=request.args.get("enable_ping") == "1",
        enable_trace=request.args.get("enable_trace") == "1",
        enable_time_skew_check=request.args.get("enable_time_skew_check") == "1",
        capture_raw_commands=request.args.get("capture_raw_commands") == "1",
        from_run_id=source_record.run_id if source_record is not None else None,
        bridge=bridge_context(source_record, profile.profile_id if profile else None),
        error_message=None,
    )


def form_state_from_request(*, error_message: str | None = None) -> dict[str, object]:
    """Build a template-ready form state from POST body values."""

    mode = normalize_mode(request.form.get("mode"))
    if mode is None:
        raise ValueError("Choose how you want to start before running diagnostics.")

    mode_option = get_mode_option(mode)
    if mode_option is None:
        raise ValueError("Unknown experience path.")

    source_record = optional_record(request.form.get("from_run_id"))

    if mode == SELF_SERVE_MODE:
        symptom = get_symptom_option(request.form.get("symptom_id"))
        if symptom is None:
            raise ValueError("Choose the option that best matches the problem first.")
        profile = self_serve_profile(symptom["id"])
    else:
        symptom = None
        profile = get_profile(request.form.get("profile_id") or "custom-profile")

    selected_checks = request.form.getlist("checks")
    targets_text = request.form.get("targets")
    dns_hosts_text = request.form.get("dns_hosts")
    effective_targets = (
        split_multiline_entries(targets_text) if targets_text else default_target_lines(profile)
    )
    effective_dns_hosts = (
        split_multiline_entries(dns_hosts_text)
        if dns_hosts_text
        else default_dns_lines(profile)
    )
    effective_checks = selected_checks or list(profile.recommended_checks if profile else [])

    return build_form_state(
        mode=mode,
        mode_option=mode_option,
        selected_symptom=symptom,
        selected_profile=profile,
        selected_checks=effective_checks,
        targets_text=targets_text or "\n".join(effective_targets),
        dns_hosts_text=dns_hosts_text or "\n".join(effective_dns_hosts),
        enable_ping=request.form.get("enable_ping") == "on",
        enable_trace=request.form.get("enable_trace") == "on",
        enable_time_skew_check=request.form.get("enable_time_skew_check") == "on",
        capture_raw_commands=request.form.get("capture_raw_commands") == "on",
        from_run_id=source_record.run_id if source_record is not None else None,
        bridge=bridge_context(source_record, profile.profile_id if profile else None),
        error_message=error_message,
    )


def request_error_form_state(error_message: str) -> dict[str, object]:
    """Best-effort form-state reconstruction after POST validation fails."""

    try:
        mode = normalize_mode(request.form.get("mode"))
    except ValueError:
        state = default_form_state()
        state["error"] = error_message
        return state

    if mode is None:
        state = default_form_state()
        state["error"] = error_message
        return state

    mode_option = get_mode_option(mode)
    if mode_option is None:
        state = default_form_state()
        state["error"] = error_message
        return state

    try:
        source_record = optional_record(request.form.get("from_run_id"))
    except ValueError:
        source_record = None

    symptom = None
    profile = None
    if mode == SELF_SERVE_MODE:
        try:
            symptom = get_symptom_option(request.form.get("symptom_id"))
        except ValueError:
            symptom = None
        profile = self_serve_profile(symptom["id"] if symptom else None)
    else:
        profile_id = request.form.get("profile_id") or "custom-profile"
        try:
            profile = get_profile(profile_id)
        except ValueError:
            profile = None

    selected_checks = request.form.getlist("checks") or list(
        profile.recommended_checks if profile is not None else []
    )
    targets_text = request.form.get("targets") or "\n".join(default_target_lines(profile))
    dns_hosts_text = request.form.get("dns_hosts") or "\n".join(default_dns_lines(profile))

    return build_form_state(
        mode=mode,
        mode_option=mode_option,
        selected_symptom=symptom,
        selected_profile=profile,
        selected_checks=selected_checks,
        targets_text=targets_text,
        dns_hosts_text=dns_hosts_text,
        enable_ping=request.form.get("enable_ping") == "on",
        enable_trace=request.form.get("enable_trace") == "on",
        enable_time_skew_check=request.form.get("enable_time_skew_check") == "on",
        capture_raw_commands=request.form.get("capture_raw_commands") == "on",
        from_run_id=source_record.run_id if source_record is not None else None,
        bridge=bridge_context(source_record, profile.profile_id if profile else None),
        error_message=error_message,
    )


def build_form_state(
    *,
    mode: str,
    mode_option: dict[str, str],
    selected_symptom: dict[str, str] | None,
    selected_profile: DiagnosticProfile | None,
    selected_checks: list[str],
    targets_text: str,
    dns_hosts_text: str,
    enable_ping: bool,
    enable_trace: bool,
    enable_time_skew_check: bool,
    capture_raw_commands: bool,
    from_run_id: str | None,
    bridge: dict[str, str] | None,
    error_message: str | None,
) -> dict[str, object]:
    """Build the single template state object used by the web UI."""

    plan = build_collection_plan(
        selected_checks=selected_checks,
        targets=split_multiline_entries(targets_text),
        dns_hosts=split_multiline_entries(dns_hosts_text),
        enable_ping=enable_ping,
        enable_trace=enable_trace,
        enable_time_skew_check=enable_time_skew_check,
        capture_raw_commands=capture_raw_commands,
    )
    return {
        "mode": mode,
        "mode_option": mode_option,
        "profile_id": selected_profile.profile_id if selected_profile is not None else None,
        "selected_profile": selected_profile,
        "selected_symptom": selected_symptom,
        "symptom_id": selected_symptom["id"] if selected_symptom is not None else None,
        "selected_checks": selected_checks,
        "checks_csv": ",".join(selected_checks) if selected_checks else None,
        "targets": split_multiline_entries(targets_text),
        "dns_hosts": split_multiline_entries(dns_hosts_text),
        "targets_text": targets_text,
        "dns_hosts_text": dns_hosts_text,
        "enable_ping": enable_ping,
        "enable_trace": enable_trace,
        "enable_time_skew_check": enable_time_skew_check,
        "capture_raw_commands": capture_raw_commands,
        "plan": plan,
        "from_run_id": from_run_id,
        "bridge": bridge,
        "error": error_message,
    }


def default_form_state() -> dict[str, object]:
    """Return the empty landing-page state."""

    return {
        "mode": None,
        "mode_option": None,
        "profile_id": None,
        "selected_profile": None,
        "selected_symptom": None,
        "symptom_id": None,
        "selected_checks": [],
        "checks_csv": None,
        "targets": [],
        "dns_hosts": [],
        "targets_text": "",
        "dns_hosts_text": "",
        "enable_ping": False,
        "enable_trace": False,
        "enable_time_skew_check": False,
        "capture_raw_commands": False,
        "plan": build_collection_plan(
            selected_checks=[],
            targets=[],
            dns_hosts=[],
            enable_ping=False,
            enable_trace=False,
            enable_time_skew_check=False,
            capture_raw_commands=False,
        ),
        "from_run_id": None,
        "bridge": None,
        "error": None,
    }


def query_previous_record() -> RunSession | None:
    """Resolve a completed source run referenced from query parameters."""

    return optional_record(request.args.get("from_run"))


def profile_catalog_context() -> tuple[list[DiagnosticProfile], list[ProfileCatalogIssue]]:
    """Return the profile list and any optional local profile issues."""

    catalog = get_profile_catalog()
    return catalog.profiles, catalog.issues


def optional_record(run_id: str | None) -> RunSession | None:
    """Resolve a prior completed run from the in-memory local session store."""

    if not run_id:
        return None
    record = get_store().get(run_id)
    if record is None:
        raise ValueError("The earlier run is no longer available in this local session.")
    if record.status != "completed" or record.result is None:
        raise ValueError("The earlier run is still in progress. Wait for its results first.")
    return record


def self_serve_profile(symptom_id: str | None) -> DiagnosticProfile | None:
    """Return the backing profile for the chosen self-serve symptom."""

    profile_id = resolve_self_serve_profile_id(symptom_id)
    return get_profile(profile_id) if profile_id else None


def default_support_profile_id(source_record: RunSession | None) -> str:
    """Choose the default support profile when entering the guided path."""

    if source_record and source_record.options.profile is not None:
        return source_record.options.profile.profile_id
    return "custom-profile"


def bridge_context(
    source_record: RunSession | None,
    current_profile_id: str | None,
) -> dict[str, str] | None:
    """Build the support-bridge context from an earlier completed run."""

    if source_record is None:
        return None

    result = cast(EndpointDiagnosticResult, source_record.result)
    suggested_profile_id = suggest_support_profile_id(
        result,
        symptom_id=source_record.experience.symptom_id,
        current_profile_id=(
            source_record.options.profile.profile_id
            if source_record.options.profile is not None
            else None
        ),
    )
    if current_profile_id == suggested_profile_id:
        suggestion_url = None
        suggestion_name = get_profile(suggested_profile_id).name
    else:
        suggestion_name = get_profile(suggested_profile_id).name
        suggestion_url = support_bridge_url(
            source_record,
            suggested_profile_id=suggested_profile_id,
        )

    top_finding = result.findings[0] if result.findings else None
    headline = (
        top_finding.plain_language or top_finding.summary
        if top_finding is not None
        else "The earlier run did not confirm a major issue."
    )
    return {
        "run_id": source_record.run_id,
        "mode_label": source_record.experience.mode_label,
        "results_url": url_for("results", run_id=source_record.run_id),
        "headline": headline,
        "suggested_profile_name": suggestion_name,
        "suggested_profile_url": suggestion_url or "",
    }


def support_bridge_url(
    record: RunSession,
    *,
    suggested_profile_id: str | None = None,
) -> str:
    """Build the support-path bridge URL for a previously completed self-serve run."""

    result = cast(EndpointDiagnosticResult, record.result)
    profile = get_profile(
        suggested_profile_id
        or suggest_support_profile_id(
            result,
            symptom_id=record.experience.symptom_id,
            current_profile_id=(
                record.options.profile.profile_id if record.options.profile is not None else None
            ),
        )
    )
    merged_checks = merge_checks(profile.recommended_checks, record.options.selected_checks)
    merged_targets = merge_targets(profile.tcp_targets, list(record.options.targets))
    merged_dns_hosts = merge_dns_hosts(profile.dns_hosts, list(record.options.dns_hosts))
    return url_for(
        "index",
        mode=SUPPORT_MODE,
        profile=profile.profile_id,
        from_run=record.run_id,
        checks=",".join(merged_checks),
        targets="\n".join(merged_targets),
        dns_hosts="\n".join(merged_dns_hosts),
        enable_ping="1" if record.options.enable_ping else "0",
        enable_trace=(
            "1"
            if record.options.enable_trace or "connectivity" in merged_checks
            else "0"
        ),
        enable_time_skew_check="1" if record.options.enable_time_skew_check else "0",
        capture_raw_commands="0",
    )


def rerun_url(record: RunSession) -> str:
    """Build the route back to the appropriate plan for a rerun."""

    base_params: dict[str, Any] = {
        "mode": record.experience.mode,
        "checks": ",".join(record.options.selected_checks),
        "targets": targets_text(record.options.targets),
        "dns_hosts": "\n".join(record.options.dns_hosts),
        "enable_ping": "1" if record.options.enable_ping else "0",
        "enable_trace": "1" if record.options.enable_trace else "0",
        "enable_time_skew_check": "1" if record.options.enable_time_skew_check else "0",
        "capture_raw_commands": "1" if record.options.capture_raw_commands else "0",
    }
    if record.experience.mode == SELF_SERVE_MODE and record.experience.symptom_id:
        return url_for("index", symptom=record.experience.symptom_id, **base_params)
    if record.experience.mode == SUPPORT_MODE:
        return url_for(
            "index",
            profile=(
                record.options.profile.profile_id
                if record.options.profile is not None
                else "custom-profile"
            ),
            **base_params,
        )
    return url_for("index", **base_params)


def merge_checks(primary: list[str], secondary: list[str]) -> list[str]:
    """Merge selected check lists while preserving earlier order."""

    return list(OrderedDict.fromkeys([*primary, *secondary]))


def merge_targets(primary: list[TcpTarget], secondary: list[TcpTarget]) -> list[str]:
    """Merge support targets while de-duplicating by host and port."""

    merged: OrderedDict[tuple[str, int], str] = OrderedDict()
    for target in [*primary, *secondary]:
        merged[(target.host, target.port)] = f"{target.host}:{target.port}"
    return list(merged.values())


def merge_dns_hosts(primary: list[str], secondary: list[str]) -> list[str]:
    """Merge DNS host lists while preserving stable order."""

    return list(OrderedDict.fromkeys([*primary, *secondary]))


def default_target_lines(profile: DiagnosticProfile | None) -> list[str]:
    """Return the default target lines for a profile-backed run form."""

    targets = (
        profile.tcp_targets
        if profile is not None and profile.tcp_targets
        else DEFAULT_TCP_TARGETS
    )
    return [f"{target.host}:{target.port}" for target in targets]


def default_dns_lines(profile: DiagnosticProfile | None) -> list[str]:
    """Return the default DNS host lines for a profile-backed run form."""

    return list(
        profile.dns_hosts
        if profile is not None and profile.dns_hosts
        else DEFAULT_DNS_HOSTS
    )


def split_multiline_entries(raw_text: str | None) -> list[str]:
    """Parse textarea-style line-delimited values into a clean list."""

    if not raw_text:
        return []
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


def targets_text(targets: tuple[TcpTarget, ...] | list[TcpTarget]) -> str:
    """Render target lines for a rerun link."""

    return "\n".join(f"{target.host}:{target.port}" for target in targets)


def resolve_redaction_level(raw_value: str | None) -> RedactionLevel:
    """Normalize the support-bundle redaction level query parameter."""

    if raw_value == "none":
        return "none"
    if raw_value == "safe":
        return "safe"
    if raw_value == "strict":
        return "strict"
    return "safe"
