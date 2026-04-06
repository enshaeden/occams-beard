"""Form parsing and route-state helpers for the local web interface."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, cast

from flask import request, url_for

from occams_beard.defaults import ALLOWED_CHECKS, DEFAULT_DNS_HOSTS, DEFAULT_TCP_TARGETS
from occams_beard.intake import (
    ClarificationPrompt,
    DecisionContext,
    DomainMappingResult,
    IntakeContext,
    IntakeResolution,
    build_clarification_questions,
    get_intake_contract,
    map_intake_to_scope,
    refine_decision_context,
    resolve_intake_interpretation,
    suggest_support_profile_id,
)
from occams_beard.models import (
    DiagnosticProfile,
    EndpointDiagnosticResult,
    RedactionLevel,
    TcpTarget,
)
from occams_beard.profile_catalog import ProfileCatalogIssue, get_profile, get_profile_catalog
from occams_beard.web.presentation.catalog import (
    SELF_SERVE_MODE,
    SUPPORT_MODE,
    get_mode_option,
    get_symptom_option,
    normalize_mode,
)
from occams_beard.web.presentation.plans import build_check_catalog
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
        intake_state = (
            resolve_self_serve_intake_state(
                symptom["id"],
                symptom_label=symptom["label"],
                clarification_source=request.args,
            )
            if symptom is not None
            else None
        )
        scope = intake_state.scope if intake_state is not None else None
        profile = (
            get_profile(scope.suggested_profile_id)
            if scope is not None and scope.suggested_profile_id
            else None
        )
    else:
        scope = None
        symptom = None
        profile = get_profile(
            request.args.get("profile") or default_support_profile_id(source_record)
        )

    base_checks = default_plan_checks(scope, profile)
    checks_csv = request.args.get("checks")
    selected_checks = (
        merge_checks(base_checks, [item for item in checks_csv.split(",") if item])
        if checks_csv
        else list(base_checks)
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
        base_checks=base_checks,
        selected_checks=selected_checks,
        targets_text=targets_text if targets_text is not None else "\n".join(effective_targets),
        dns_hosts_text=(
            dns_hosts_text if dns_hosts_text is not None else "\n".join(effective_dns_hosts)
        ),
        enable_ping=request.args.get("enable_ping") == "1",
        enable_trace=request.args.get("enable_trace") == "1",
        enable_time_skew_check=request.args.get("enable_time_skew_check") == "1",
        capture_raw_commands=request.args.get("capture_raw_commands") == "1",
        intake_context=(
            intake_state.intake_context if mode == SELF_SERVE_MODE and intake_state else None
        ),
        clarification=(
            intake_state.clarification if mode == SELF_SERVE_MODE and intake_state else None
        ),
        plan_preview=(
            intake_state.plan_preview if mode == SELF_SERVE_MODE and intake_state else None
        ),
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
        intake_state = resolve_self_serve_intake_state(
            symptom["id"],
            symptom_label=symptom["label"],
            clarification_source=request.form,
        )
        scope = intake_state.scope
        profile = get_profile(scope.suggested_profile_id) if scope.suggested_profile_id else None
    else:
        intake_state = None
        scope = None
        symptom = None
        profile = get_profile(request.form.get("profile_id") or "custom-profile")

    base_checks = default_plan_checks(scope, profile)
    selected_checks = submitted_check_selection(base_checks=base_checks, source=request.form)
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
    has_explicit_additions = bool(request.form.getlist("extra_checks")) or (
        request.form.get("select_all_extra_checks") == "1"
    )
    enforce_intake_scope = (
        mode != SELF_SERVE_MODE
        or not has_explicit_additions
        or not has_check_selection_changes(base_checks, selected_checks)
    )
    return build_form_state(
        mode=mode,
        mode_option=mode_option,
        selected_symptom=symptom,
        selected_profile=profile,
        base_checks=base_checks,
        selected_checks=selected_checks,
        targets_text=targets_text or "\n".join(effective_targets),
        dns_hosts_text=dns_hosts_text or "\n".join(effective_dns_hosts),
        enable_ping=request.form.get("enable_ping") == "on",
        enable_trace=request.form.get("enable_trace") == "on",
        enable_time_skew_check=request.form.get("enable_time_skew_check") == "on",
        capture_raw_commands=request.form.get("capture_raw_commands") == "on",
        intake_context=intake_state.intake_context if intake_state is not None else None,
        clarification=intake_state.clarification if intake_state is not None else None,
        plan_preview=intake_state.plan_preview if intake_state is not None else None,
        from_run_id=source_record.run_id if source_record is not None else None,
        bridge=bridge_context(source_record, profile.profile_id if profile else None),
        enforce_intake_scope=enforce_intake_scope,
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
        intake_state = (
            resolve_self_serve_intake_state(
                symptom["id"],
                symptom_label=symptom["label"],
                clarification_source=request.form,
            )
            if symptom is not None
            else None
        )
        scope = intake_state.scope if intake_state is not None else None
        profile = (
            get_profile(scope.suggested_profile_id)
            if scope is not None and scope.suggested_profile_id
            else None
        )
    else:
        intake_state = None
        scope = None
        profile_id = request.form.get("profile_id") or "custom-profile"
        try:
            profile = get_profile(profile_id)
        except ValueError:
            profile = None

    base_checks = default_plan_checks(scope, profile)
    selected_checks = submitted_check_selection(base_checks=base_checks, source=request.form)
    targets_text = request.form.get("targets") or "\n".join(default_target_lines(profile))
    dns_hosts_text = request.form.get("dns_hosts") or "\n".join(default_dns_lines(profile))

    return build_form_state(
        mode=mode,
        mode_option=mode_option,
        selected_symptom=symptom,
        selected_profile=profile,
        base_checks=base_checks,
        selected_checks=selected_checks,
        targets_text=targets_text,
        dns_hosts_text=dns_hosts_text,
        enable_ping=request.form.get("enable_ping") == "on",
        enable_trace=request.form.get("enable_trace") == "on",
        enable_time_skew_check=request.form.get("enable_time_skew_check") == "on",
        capture_raw_commands=request.form.get("capture_raw_commands") == "on",
        intake_context=intake_state.intake_context if intake_state is not None else None,
        clarification=intake_state.clarification if intake_state is not None else None,
        plan_preview=intake_state.plan_preview if intake_state is not None else None,
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
    base_checks: list[str],
    selected_checks: list[str],
    targets_text: str,
    dns_hosts_text: str,
    enable_ping: bool,
    enable_trace: bool,
    enable_time_skew_check: bool,
    capture_raw_commands: bool,
    intake_context: IntakeContext | None,
    clarification: dict[str, object] | None,
    plan_preview: dict[str, str] | None,
    from_run_id: str | None,
    bridge: dict[str, str] | None,
    error_message: str | None,
    enforce_intake_scope: bool | None = None,
) -> dict[str, object]:
    """Build the single template state object used by the web UI."""

    normalized_base_checks = ordered_supported_checks(base_checks)
    normalized_selected_checks = ordered_supported_checks(selected_checks)
    effective_targets = split_multiline_entries(targets_text)
    effective_dns_hosts = split_multiline_entries(dns_hosts_text)
    plan = build_collection_plan(
        selected_checks=normalized_base_checks,
        targets=effective_targets,
        dns_hosts=effective_dns_hosts,
        enable_ping=enable_ping,
        enable_trace=enable_trace,
        enable_time_skew_check=enable_time_skew_check,
        capture_raw_commands=capture_raw_commands,
    )
    effective_plan = build_collection_plan(
        selected_checks=normalized_selected_checks,
        targets=effective_targets,
        dns_hosts=effective_dns_hosts,
        enable_ping=enable_ping,
        enable_trace=enable_trace,
        enable_time_skew_check=enable_time_skew_check,
        capture_raw_commands=capture_raw_commands,
    )
    customization = build_customization_state(
        mode=mode,
        included_checks=normalized_base_checks,
        selected_checks=normalized_selected_checks,
    )
    normalized_raw_selected_checks = dedupe_checks(selected_checks)
    return {
        "mode": mode,
        "mode_option": mode_option,
        "profile_id": selected_profile.profile_id if selected_profile is not None else None,
        "selected_profile": selected_profile,
        "selected_symptom": selected_symptom,
        "symptom_id": selected_symptom["id"] if selected_symptom is not None else None,
        "base_checks": normalized_base_checks,
        "selected_checks": normalized_raw_selected_checks,
        "checks_csv": (
            ",".join(normalized_raw_selected_checks)
            if normalized_raw_selected_checks
            else None
        ),
        "targets": effective_targets,
        "dns_hosts": effective_dns_hosts,
        "targets_text": targets_text,
        "dns_hosts_text": dns_hosts_text,
        "enable_ping": enable_ping,
        "enable_trace": enable_trace,
        "enable_time_skew_check": enable_time_skew_check,
        "capture_raw_commands": capture_raw_commands,
        "intake_context": intake_context,
        "clarification": clarification,
        "plan_preview": plan_preview,
        "plan": plan,
        "effective_plan": effective_plan,
        "customization": customization,
        "enforce_intake_scope": (
            enforce_intake_scope
            if enforce_intake_scope is not None
            else mode != SELF_SERVE_MODE or not customization["has_changes"]
        ),
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
        "base_checks": [],
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
        "intake_context": None,
        "clarification": None,
        "plan_preview": None,
        "plan": build_collection_plan(
            selected_checks=[],
            targets=[],
            dns_hosts=[],
            enable_ping=False,
            enable_trace=False,
            enable_time_skew_check=False,
            capture_raw_commands=False,
        ),
        "effective_plan": build_collection_plan(
            selected_checks=[],
            targets=[],
            dns_hosts=[],
            enable_ping=False,
            enable_trace=False,
            enable_time_skew_check=False,
            capture_raw_commands=False,
        ),
        "customization": build_customization_state(
            mode=SELF_SERVE_MODE,
            included_checks=[],
            selected_checks=[],
        ),
        "enforce_intake_scope": True,
        "from_run_id": None,
        "bridge": None,
        "error": None,
    }


def default_plan_checks(
    scope: DomainMappingResult | None,
    profile: DiagnosticProfile | None,
) -> list[str]:
    """Return the base guided plan checks for the current mode context."""

    if scope is not None:
        return list(scope.selected_checks)
    if profile is not None:
        return list(profile.recommended_checks)
    return []


def submitted_check_selection(
    *,
    base_checks: list[str],
    source: Any,
) -> list[str]:
    """Resolve submitted advanced check additions while preserving legacy posts."""

    if source.get("select_all_extra_checks") == "1":
        return list(ALLOWED_CHECKS)
    extra_checks = source.getlist("extra_checks")
    if extra_checks:
        return merge_checks(base_checks, extra_checks)
    legacy_checks = source.getlist("checks")
    if legacy_checks:
        return dedupe_checks(legacy_checks)
    return list(base_checks)


def dedupe_checks(checks: list[str]) -> list[str]:
    """De-duplicate submitted check identifiers while preserving order."""

    return list(OrderedDict.fromkeys(checks))


def ordered_supported_checks(checks: list[str]) -> list[str]:
    """Return supported checks in canonical UI order."""

    selected = set(checks)
    return [check for check in ALLOWED_CHECKS if check in selected]


def additional_check_options(base_checks: list[str]) -> list[str]:
    """Return checks that can be added on top of the guided plan."""

    base_set = set(ordered_supported_checks(base_checks))
    return [check for check in ALLOWED_CHECKS if check not in base_set]


def has_check_selection_changes(base_checks: list[str], selected_checks: list[str]) -> bool:
    """Return True when the current selection differs from the guided plan."""

    return set(ordered_supported_checks(base_checks)) != set(ordered_supported_checks(selected_checks))


def build_customization_state(
    *,
    mode: str,
    included_checks: list[str],
    selected_checks: list[str],
) -> dict[str, object]:
    """Build the advanced customization view model for the form."""

    base_label = "recommended plan" if mode == SELF_SERVE_MODE else "support plan"
    catalog = build_check_catalog(
        included_checks=included_checks,
        selected_checks=selected_checks,
        included_badge_label=(
            "Included by recommended plan"
            if mode == SELF_SERVE_MODE
            else "Included by support plan"
        ),
    )
    manual_additions = cast(int, catalog["manual_addition_count"])
    omitted_included = cast(int, catalog["omitted_included_count"])
    kept_included = cast(int, catalog["kept_included_count"])
    available_addition_count = len(additional_check_options(included_checks))
    all_extra_checks_selected = (
        available_addition_count > 0 and manual_additions == available_addition_count
    )
    has_changes = manual_additions > 0 or omitted_included > 0

    if all_extra_checks_selected:
        summary_title = "All test areas selected"
        summary_body = f"Current run keeps the {base_label} and adds every remaining test area."
    elif manual_additions > 0:
        summary_title = "Plan plus added test areas"
        summary_body = (
            f"Current run keeps the {base_label} and adds "
            f"{count_label(manual_additions, 'additional test area')}."
        )
    elif omitted_included > 0:
        summary_title = "Customized plan"
        summary_body = f"Current run differs from the {base_label}."
    else:
        summary_title = "Guided plan"
        summary_body = f"Current run uses the {base_label} as-is."

    summary_parts = [
        f"{count_label(kept_included, 'check area')} kept from the {base_label}",
    ]
    if manual_additions > 0:
        summary_parts.append(f"{count_label(manual_additions, 'check area')} added manually")
    if omitted_included > 0:
        summary_parts.append(
            f"{count_label(omitted_included, 'check area')} removed from the {base_label}"
        )

    return {
        **catalog,
        "base_label": base_label,
        "has_changes": has_changes,
        "all_extra_checks_selected": all_extra_checks_selected,
        "available_addition_count": available_addition_count,
        "summary_title": summary_title,
        "summary_body": summary_body,
        "summary_detail": "; ".join(summary_parts) + ".",
    }


def count_label(count: int, label: str) -> str:
    """Return a compact count label with pluralization."""

    suffix = "" if count == 1 else "s"
    return f"{count} {label}{suffix}"


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


def resolve_self_serve_intake_state(
    symptom_id: str | None,
    *,
    symptom_label: str | None = None,
    clarification_source: Any | None = None,
):
    """Resolve intake scope and preserve the rationale context for execution."""

    resolution = resolve_intake_interpretation(symptom_id)
    context = clarification_context_from_submission(
        intent_key=resolution.primary_intent,
        clarification_source=clarification_source,
    )
    scope = map_intake_to_scope(
        resolution=resolution,
        contract=get_intake_contract(),
        context=context,
    )
    clarification = clarification_template_state(context)
    plan_preview = build_plan_preview(scope, symptom_label=symptom_label, context=context)
    return SelfServeIntakeState(
        scope=scope,
        clarification=clarification,
        plan_preview=plan_preview,
        intake_context=build_intake_context(
            symptom_id=symptom_id,
            symptom_label=symptom_label,
            resolution=resolution,
            context=context,
            scope=scope,
        ),
    )


@dataclass(frozen=True, slots=True)
class SelfServeIntakeState:
    """Resolved self-serve scope plus stable intake context."""

    scope: DomainMappingResult
    clarification: dict[str, object] | None
    plan_preview: dict[str, str] | None
    intake_context: IntakeContext


def build_intake_context(
    *,
    symptom_id: str | None,
    symptom_label: str | None,
    resolution: IntakeResolution,
    context: DecisionContext | None,
    scope: DomainMappingResult,
) -> IntakeContext:
    """Build the typed run-context payload describing intake decisions."""

    return IntakeContext(
        selected_symptom_key=symptom_id,
        selected_symptom_label=symptom_label,
        resolved_intent_key=resolution.primary_intent,
        clarification_answers=context.answered if context is not None else (),
        scope_rationale=intake_scope_rationale(resolution, context, scope),
        trace_metadata={
            "resolved_intent": {
                "intent_key": resolution.primary_intent,
                "confidence_score": resolution.confidence_score,
                "alternative_intents": list(resolution.alternative_intents),
                "match_rule": resolution.trace.get("match_rule"),
            },
            "clarification_path": {
                "asked_questions": [prompt.key for prompt in context.asked_questions]
                if context is not None
                else [],
                "answers": list(context.answered) if context is not None else [],
                "selected_pathway_key": (
                    context.selected_pathway_key if context is not None else None
                ),
                "status": context.status if context is not None else None,
                "reason": context.reason if context is not None else None,
            },
            "domain_mapping": {
                "selected_domains": list(scope.selected_domains),
                "selected_checks": list(scope.selected_checks),
                "suggested_profile_id": scope.suggested_profile_id,
                "fallback_mode": scope.fallback_mode,
                "rationale": scope.rationale,
            },
        },
    )


def intake_scope_rationale(
    resolution: IntakeResolution,
    context: DecisionContext | None,
    scope: DomainMappingResult,
) -> str:
    """Return a compact machine-readable rationale for the chosen scope."""

    if scope.rationale and scope.rationale != "unspecified":
        return scope.rationale
    if context is not None and context.reason:
        return context.reason
    if not resolution.primary_intent:
        return "fallback_general_triage"
    return "intent_default_scope"


def clarification_context_from_submission(
    *,
    intent_key: str | None,
    clarification_source: Any | None,
) -> DecisionContext | None:
    """Build an optional refined context from submitted clarification answers."""

    question_set = build_clarification_questions(intent_key)
    context = question_set.context
    if not context.asked_questions:
        return None

    answered_any = False
    for prompt in context.asked_questions:
        answer = clarification_value(clarification_source, prompt.key)
        if not answer:
            continue
        updated_context, error = refine_decision_context(
            context,
            question_key=prompt.key,
            answer=answer,
        )
        if error is not None:
            continue
        answered_any = True
        context = updated_context
    return context if answered_any else None


def clarification_value(source: Any | None, question_key: str) -> str | None:
    """Read one clarification value from form or query sources."""

    if source is None:
        return None
    getter = getattr(source, "get", None)
    if not callable(getter):
        return None
    raw_value = getter(f"clar_{question_key}")
    return cast(str | None, raw_value)


def clarification_template_state(context: DecisionContext | None) -> dict[str, object] | None:
    """Build template state for showing one minimal clarification prompt."""

    if context is None or not context.asked_questions:
        return None

    next_prompt = next_unanswered_prompt(context)
    answered = [
        {
            "key": key,
            "prompt": prompt_text_for(context.asked_questions, key),
            "answer": answer,
            "answer_label": user_facing_option(answer),
        }
        for key, answer in context.answered
    ]
    query_values = [f"clar_{key}={answer}" for key, answer in context.answered]
    return {
        "question": prompt_template(next_prompt) if next_prompt is not None else None,
        "answered": answered,
        "query_values": query_values,
        "has_pending_question": next_prompt is not None,
    }


def prompt_template(prompt: ClarificationPrompt) -> dict[str, object]:
    """Render one clarification prompt for template use."""

    return {
        "key": prompt.key,
        "prompt": prompt.prompt,
        "options": [
            {
                "value": option,
                "label": user_facing_option(option),
            }
            for option in prompt.options
        ],
    }


def next_unanswered_prompt(context: DecisionContext) -> ClarificationPrompt | None:
    """Return the next prompt in sequence that still needs an answer."""

    remaining = set(context.remaining_question_keys)
    for prompt in context.asked_questions:
        if prompt.key in remaining:
            return prompt
    return None


def prompt_text_for(prompts: tuple[ClarificationPrompt, ...], key: str) -> str:
    """Return prompt text for a question key when available."""

    for prompt in prompts:
        if prompt.key == key:
            return prompt.prompt
    return key.replace("_", " ").capitalize()


def user_facing_option(value: str) -> str:
    """Convert contract option tokens into readable user-facing labels."""

    tokens = value.replace("/", " ").replace("_", " ").split()
    if not tokens:
        return value
    return " ".join(tokens).capitalize()


def build_plan_preview(
    scope: DomainMappingResult,
    *,
    symptom_label: str | None,
    context: DecisionContext | None,
) -> dict[str, str]:
    """Build a short plain-language explanation shown before execution."""

    top_checks = ", ".join(scope.selected_checks[:3])
    if len(scope.selected_checks) > 3:
        top_checks = f"{top_checks}, and related checks"
    because = symptom_label or "the symptom you selected"
    if context is not None and context.answered:
        latest_answer = user_facing_option(context.answered[-1][1]).lower()
        because = f"{because} and your clarification answer ({latest_answer})"
    return {
        "check_areas": top_checks or "baseline device checks",
        "because": because,
    }


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
