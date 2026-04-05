"""CLI orchestration for Occam's Beard."""

from __future__ import annotations

import argparse
import logging
import sys

from occams_beard.defaults import (
    ALLOWED_CHECKS,
)
from occams_beard.profile_catalog import get_profile_catalog
from occams_beard.report import render_report
from occams_beard.runner import build_run_options, run_diagnostics
from occams_beard.serializers import write_json_file
from occams_beard.support_bundle import write_support_bundle

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        prog="occams-beard",
        usage="occams-beard run [options]",
        description="Single operator-facing command for host and network diagnostics.",
        epilog="Use 'occams-beard run --help' for the full run workflow and options.",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")

    run_parser = subparsers.add_parser(
        "run",
        help="Run the default diagnostic suite.",
        description=(
            "Run host and network diagnostics.\n"
            "With no flags, the default suite runs against built-in DNS and TCP targets "
            "and prints a human-readable report."
        ),
        epilog=_run_examples_text(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run_parser.set_defaults(handler=_run_command)

    scope_group = run_parser.add_argument_group("Scope")
    scope_group.add_argument(
        "--checks",
        metavar="LIST",
        help=(
            f"Comma-separated diagnostic domains. Supported values: {', '.join(ALLOWED_CHECKS)}."
        ),
    )

    target_group = run_parser.add_argument_group("Targets")
    target_group.add_argument(
        "--target",
        metavar="HOST:PORT",
        action="append",
        default=[],
        help="Repeat to add TCP targets as host:port.",
    )
    target_group.add_argument(
        "--target-file",
        metavar="PATH",
        help=(
            "Load TCP targets from a JSON array of host:port strings or "
            "{host, port, label} objects."
        ),
    )
    target_group.add_argument(
        "--dns-host",
        metavar="HOST",
        action="append",
        default=[],
        help="Repeat to add DNS resolution hostnames.",
    )
    target_group.add_argument(
        "--profile",
        metavar="PROFILE_ID",
        help="Use a built-in or local diagnostics profile as the default issue scenario.",
    )
    target_group.add_argument(
        "--list-profiles",
        action="store_true",
        help="List available built-in and local profiles and exit.",
    )

    output_group = run_parser.add_argument_group("Output")
    output_group.add_argument(
        "--json-out",
        metavar="PATH",
        help="Write structured JSON output to PATH.",
    )
    output_group.add_argument(
        "--support-bundle",
        metavar="PATH",
        help=(
            "Write a support bundle to PATH. Use a .zip suffix for a zip "
            "archive or a directory path for loose files."
        ),
    )
    output_group.add_argument(
        "--redaction-level",
        choices=["none", "safe", "strict"],
        default="safe",
        help="Redaction level for support bundle export. Default: safe.",
    )
    output_group.add_argument(
        "--bundle-include-raw",
        action="store_true",
        help="Capture and include raw command output in the support bundle. Off by default.",
    )
    output_group.add_argument(
        "--suppress-report",
        action="store_true",
        help="Skip the human-readable terminal report.",
    )

    probe_group = run_parser.add_argument_group("Optional probes")
    probe_group.add_argument(
        "--enable-ping",
        action="store_true",
        help="Enable best-effort ping checks.",
    )
    probe_group.add_argument(
        "--enable-trace",
        action="store_true",
        help="Enable best-effort traceroute or tracert checks.",
    )
    probe_group.add_argument(
        "--enable-time-skew-check",
        action="store_true",
        help=(
            "Enable a bounded external clock-reference check using one HTTPS response date. "
            "This creates network traffic."
        ),
    )

    logging_group = run_parser.add_argument_group("Logging")
    logging_group.add_argument("--verbose", action="store_true", help="Enable INFO-level logging.")
    logging_group.add_argument("--debug", action="store_true", help="Enable DEBUG-level logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""

    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        return 2

    _configure_logging(verbose=args.verbose, debug=args.debug)

    try:
        return handler(args)
    except ValueError as exc:
        parser.error(str(exc))
    except Exception as exc:  # pragma: no cover - exercised through exit path tests.
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            LOGGER.exception("Diagnostics execution failed.")
        else:
            LOGGER.error("Diagnostics execution failed: %s", exc)
        return 1


def _run_command(args: argparse.Namespace) -> int:
    if getattr(args, "list_profiles", False):
        catalog = get_profile_catalog()
        for profile in catalog.profiles:
            print(
                f"{profile.profile_id}\t{profile.issue_category}\t{profile.name}\t{profile.description}"
            )
        for issue in catalog.issues:
            print(
                f"Skipped {issue.source} profile file {issue.path}: {issue.reason}.",
                file=sys.stderr,
            )
        return 0

    options = build_run_options(
        checks=args.checks,
        targets=args.target,
        target_file=args.target_file,
        dns_hosts=args.dns_host,
        profile_id=getattr(args, "profile", None),
        enable_ping=args.enable_ping,
        enable_trace=args.enable_trace,
        enable_time_skew_check=getattr(args, "enable_time_skew_check", False),
        capture_raw_commands=getattr(args, "bundle_include_raw", False),
    )
    LOGGER.info(
        "Running host and network diagnostics for checks: %s", ", ".join(options.selected_checks)
    )
    LOGGER.debug(
        "Diagnostics input summary: tcp_targets=%d dns_hosts=%d json_out=%s support_bundle=%s "
        "suppress_report=%s enable_ping=%s enable_trace=%s enable_time_skew_check=%s "
        "profile=%s raw_capture=%s",
        len(options.targets),
        len(options.dns_hosts),
        bool(args.json_out),
        bool(getattr(args, "support_bundle", None)),
        args.suppress_report,
        options.enable_ping,
        options.enable_trace,
        options.enable_time_skew_check,
        options.profile.profile_id if options.profile else None,
        options.capture_raw_commands,
    )
    result = run_diagnostics(options)

    json_path = None
    if args.json_out:
        json_path = str(write_json_file(result, args.json_out))

    if getattr(args, "support_bundle", None):
        write_support_bundle(
            result,
            args.support_bundle,
            redaction_level=getattr(args, "redaction_level", "safe"),
            include_raw_command_capture=getattr(args, "bundle_include_raw", False),
        )

    if not args.suppress_report:
        print(render_report(result, json_path=json_path))

    return 0


def _configure_logging(verbose: bool, debug: bool) -> None:
    level = logging.WARNING
    if verbose:
        level = logging.INFO
    if debug:
        level = logging.DEBUG
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )


def _run_examples_text() -> str:
    """Return operator-oriented example commands for run help output."""

    return (
        "Examples:\n"
        "  occams-beard run\n"
        "  occams-beard run --json-out report.json\n"
        "  occams-beard run --list-profiles\n"
        "  occams-beard run --profile no-internet\n"
        "  occams-beard run --support-bundle bundle.zip --redaction-level safe\n"
        "  occams-beard run --checks network,dns,connectivity\n"
        "  occams-beard run --target github.com:443 --target 1.1.1.1:53\n"
        "  occams-beard run --target-file sample_output/example-targets.json\n"
        "  occams-beard run --checks time --enable-time-skew-check\n"
        "  occams-beard run --enable-ping --enable-trace --verbose\n"
        "  occams-beard run --suppress-report --json-out report.json"
    )
