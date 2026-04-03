#!/usr/bin/env python3
"""Run bounded live smoke validation on the current host."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    """Run live smoke validation and optionally persist a summary."""

    from occams_beard.live_smoke import SmokeValidationError, run_live_smoke

    parser = argparse.ArgumentParser(
        description="Run bounded live smoke validation on the current host."
    )
    parser.add_argument(
        "--json-out",
        metavar="PATH",
        help="Optional path for a non-sensitive smoke summary JSON file.",
    )
    args = parser.parse_args(argv)

    try:
        _result, summary = run_live_smoke()
    except SmokeValidationError as exc:
        print(f"Live smoke validation failed: {exc}", file=sys.stderr)
        return 1

    summary_text = json.dumps(summary, indent=2) + "\n"
    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(summary_text, encoding="utf-8")
    print(summary_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
