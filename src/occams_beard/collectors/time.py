"""Clock and timezone collection for bounded local diagnostics."""

from __future__ import annotations

import os
import ssl
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from occams_beard.defaults import DEFAULT_TIME_REFERENCE_LABEL, DEFAULT_TIME_REFERENCE_URL
from occams_beard.models import ClockSkewCheck, DiagnosticWarning, TimeState
from occams_beard.platform import windows
from occams_beard.platform.common import current_platform

_TIME_REFERENCE_TIMEOUT_SECONDS = 5.0
_ZONEINFO_MARKER = "zoneinfo/"


def collect_time_state(
    *,
    enable_skew_check: bool = False,
    reference_label: str = DEFAULT_TIME_REFERENCE_LABEL,
    reference_url: str = DEFAULT_TIME_REFERENCE_URL,
    progress_callback=None,
) -> tuple[TimeState, list[DiagnosticWarning]]:
    """Collect local clock state and an optional bounded skew check."""

    warnings: list[DiagnosticWarning] = []
    observed_local = _observed_local_now()
    timezone_identifier, timezone_source = _read_timezone_identifier(
        platform_name=current_platform(),
        observed_local=observed_local,
    )
    time_state = TimeState(
        local_time_iso=observed_local.isoformat(),
        utc_time_iso=observed_local.astimezone(UTC).isoformat(),
        timezone_name=observed_local.tzname(),
        timezone_identifier=timezone_identifier,
        timezone_identifier_source=timezone_source,
        utc_offset_minutes=_utc_offset_minutes(observed_local),
        timezone_offset_consistent=_timezone_offset_consistent(
            observed_local=observed_local,
            timezone_identifier=timezone_identifier,
        ),
        skew_check=ClockSkewCheck(
            status="not_run",
            reference_kind="https-date-header",
            reference_label=reference_label,
            reference_url=reference_url,
        ),
    )
    if progress_callback is not None:
        progress_callback(1)

    if not enable_skew_check:
        return time_state, warnings

    skew_check = _perform_clock_skew_check(
        reference_label=reference_label,
        reference_url=reference_url,
    )
    time_state.skew_check = skew_check
    if skew_check.status != "checked":
        warnings.append(
            DiagnosticWarning(
                domain="time",
                code="clock-skew-check-failed",
                message=(
                    "The bounded external clock-reference check could not confirm skew: "
                    f"{skew_check.error or 'unknown-error'}."
                ),
            )
        )
    if progress_callback is not None:
        progress_callback(2)
    return time_state, warnings


def _observed_local_now() -> datetime:
    return datetime.now().astimezone()


def _utc_offset_minutes(observed_local: datetime) -> int | None:
    offset = observed_local.utcoffset()
    if offset is None:
        return None
    return int(offset.total_seconds() // 60)


def _read_timezone_identifier(
    *,
    platform_name: str,
    observed_local: datetime,
) -> tuple[str | None, str | None]:
    tzinfo_key = getattr(observed_local.tzinfo, "key", None)
    if isinstance(tzinfo_key, str) and tzinfo_key.strip():
        return tzinfo_key.strip(), "tzinfo-key"

    env_tz = os.environ.get("TZ")
    if isinstance(env_tz, str) and env_tz.strip():
        return env_tz.strip(), "environment"

    if platform_name == "windows":
        identifier = windows.read_timezone_identifier()
        if identifier is not None:
            return identifier, "tzutil"
        return None, None

    file_timezone = _read_text_timezone(Path("/etc/timezone"))
    if file_timezone is not None:
        return file_timezone, "etc-timezone"

    localtime_timezone = _read_localtime_timezone(Path("/etc/localtime"))
    if localtime_timezone is not None:
        return localtime_timezone, "localtime-symlink"

    return None, None


def _read_text_timezone(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        raw_value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return raw_value or None


def _read_localtime_timezone(path: Path) -> str | None:
    try:
        if not path.exists() or not path.is_symlink():
            return None
        resolved = str(path.resolve())
    except OSError:
        return None
    marker_index = resolved.find(_ZONEINFO_MARKER)
    if marker_index == -1:
        return None
    candidate = resolved[marker_index + len(_ZONEINFO_MARKER) :].strip("/")
    return candidate or None


def _timezone_offset_consistent(
    *,
    observed_local: datetime,
    timezone_identifier: str | None,
) -> bool | None:
    if timezone_identifier is None or "/" not in timezone_identifier:
        if timezone_identifier == "UTC":
            return _utc_offset_minutes(observed_local) == 0
        return None
    try:
        zone = ZoneInfo(timezone_identifier)
    except ZoneInfoNotFoundError:
        return None
    zone_offset = observed_local.astimezone(zone).utcoffset()
    observed_offset = observed_local.utcoffset()
    if zone_offset is None or observed_offset is None:
        return None
    return zone_offset == observed_offset


def _perform_clock_skew_check(
    *,
    reference_label: str,
    reference_url: str,
) -> ClockSkewCheck:
    request = urllib_request.Request(
        reference_url,
        method="HEAD",
        headers={"User-Agent": "occams-beard/time-check"},
    )
    context = _ssl_context_for_reference(reference_url)
    start_perf = time.perf_counter()
    start_utc = datetime.now(UTC)
    try:
        with urllib_request.urlopen(
            request,
            timeout=_TIME_REFERENCE_TIMEOUT_SECONDS,
            context=context,
        ) as response:
            end_utc = datetime.now(UTC)
            duration_ms = int((time.perf_counter() - start_perf) * 1000)
            reference_time = _parse_reference_time(response.headers.get("Date"))
            if reference_time is None:
                return ClockSkewCheck(
                    status="failed",
                    reference_kind="https-date-header",
                    reference_label=reference_label,
                    reference_url=reference_url,
                    duration_ms=duration_ms,
                    error="missing-date-header",
                )
            midpoint_utc = start_utc + ((end_utc - start_utc) / 2)
            skew_seconds = round((midpoint_utc - reference_time).total_seconds(), 1)
            absolute_skew_seconds = round(abs(skew_seconds), 1)
            return ClockSkewCheck(
                status="checked",
                reference_kind="https-date-header",
                reference_label=reference_label,
                reference_url=reference_url,
                reference_time_iso=reference_time.isoformat(),
                observed_at_utc_iso=midpoint_utc.isoformat(),
                skew_seconds=skew_seconds,
                absolute_skew_seconds=absolute_skew_seconds,
                duration_ms=duration_ms,
            )
    except urllib_error.HTTPError as exc:
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
        return ClockSkewCheck(
            status="failed",
            reference_kind="https-date-header",
            reference_label=reference_label,
            reference_url=reference_url,
            duration_ms=duration_ms,
            error=f"http-{exc.code}",
        )
    except urllib_error.URLError as exc:
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
        return ClockSkewCheck(
            status="failed",
            reference_kind="https-date-header",
            reference_label=reference_label,
            reference_url=reference_url,
            duration_ms=duration_ms,
            error=_normalize_reference_error(exc.reason),
        )
    except ValueError:
        duration_ms = int((time.perf_counter() - start_perf) * 1000)
        return ClockSkewCheck(
            status="failed",
            reference_kind="https-date-header",
            reference_label=reference_label,
            reference_url=reference_url,
            duration_ms=duration_ms,
            error="invalid-reference-response",
        )


def _parse_reference_time(raw_value: str | None) -> datetime | None:
    if raw_value is None:
        return None
    parsed = parsedate_to_datetime(raw_value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _ssl_context_for_reference(reference_url: str):
    scheme = urllib_parse.urlparse(reference_url).scheme.lower()
    if scheme != "https":
        return None
    return ssl._create_unverified_context()


def _normalize_reference_error(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip().replace(" ", "-").lower()
    return "reference-unreachable"
