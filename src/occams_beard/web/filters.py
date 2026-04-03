"""Template filters used by the local Flask interface."""

from __future__ import annotations

from flask import Flask


def register_template_filters(app: Flask) -> None:
    """Register formatting helpers used by the local HTML templates."""

    app.add_template_filter(format_bytes, "format_bytes")
    app.add_template_filter(format_percent, "format_percent")
    app.add_template_filter(format_latency, "format_latency")
    app.add_template_filter(join_addresses, "join_addresses")
    app.add_template_filter(yes_no, "yes_no")


def format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    suffixes = ["B", "KiB", "MiB", "GiB", "TiB"]
    size = float(value)
    for suffix in suffixes:
        if size < 1024 or suffix == suffixes[-1]:
            return f"{size:.1f} {suffix}"
        size /= 1024
    return f"{value} B"


def format_percent(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f}%"


def format_latency(value: float | None) -> str:
    if value is None:
        return "unknown"
    return f"{value:.1f} ms"


def join_addresses(values: list[str]) -> str:
    return ", ".join(values) if values else "none detected"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"
