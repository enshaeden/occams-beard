"""Cross-platform bootstrap for the repo-root operator launchers."""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

LOGGER = logging.getLogger(__name__)
MINIMUM_PYTHON_VERSION = (3, 11)


def build_parser() -> argparse.ArgumentParser:
    """Build the repo-root launcher parser."""

    parser = argparse.ArgumentParser(
        prog="open-device-check-root-launcher",
        description="Bootstrap the local operator environment and run the operator launcher.",
    )
    parser.add_argument(
        "--project-root",
        help="Explicit project root. Defaults to the repository root inferred from this file.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable INFO-level logging.")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG-level logging.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Bootstrap a local environment and delegate to the Python launcher."""

    parser = build_parser()
    args, forwarded_args = parser.parse_known_args(list(argv) if argv is not None else None)
    _configure_logging(verbose=args.verbose, debug=args.debug)

    project_root = _resolve_project_root(args.project_root)
    if forwarded_args and forwarded_args[0] == "--":
        forwarded_args = forwarded_args[1:]

    return bootstrap_and_launch(project_root, forwarded_args)


def bootstrap_and_launch(project_root: Path, launcher_args: Sequence[str]) -> int:
    """Ensure the project environment exists, then run the operator launcher."""

    bootstrap_python = _resolve_bootstrap_python(project_root)
    if not _launcher_dependencies_ready(project_root, bootstrap_python):
        LOGGER.info("Bootstrapping local project environment: project_root=%s", project_root)
        _bootstrap_local_environment(project_root, bootstrap_python)

    project_python = _resolve_project_python(project_root)
    command = [str(project_python), "-m", "occams_beard.launcher", *launcher_args]
    LOGGER.info("Launching operator interface: command=%s", command)
    result = subprocess.run(
        command,
        cwd=project_root,
        env=_build_runtime_environment(project_root),
        check=False,
    )
    return int(result.returncode)


def _resolve_project_root(project_root: str | None) -> Path:
    if project_root:
        return Path(project_root).resolve()
    return Path(__file__).resolve().parents[2]


def _resolve_bootstrap_python(project_root: Path) -> Path:
    project_python = _project_python_candidate(project_root)
    if project_python.exists() and _python_version_supported(project_python):
        return project_python

    if sys.executable and _python_version_supported(Path(sys.executable)):
        return Path(sys.executable)

    raise RuntimeError(
        "Unable to determine a Python 3.11+ interpreter for environment bootstrap."
    )


def _resolve_project_python(project_root: Path) -> Path:
    project_python = _project_python_candidate(project_root)
    if project_python.exists() and _python_version_supported(project_python):
        return project_python
    return _resolve_bootstrap_python(project_root)


def _project_python_candidate(project_root: Path) -> Path:
    if os.name == "nt":
        return project_root / ".venv" / "Scripts" / "python.exe"
    return project_root / ".venv" / "bin" / "python3"


def _python_version_supported(python_bin: Path) -> bool:
    result = subprocess.run(
        [
            str(python_bin),
            "-c",
            (
                "import sys; "
                f"raise SystemExit(0 if sys.version_info >= {MINIMUM_PYTHON_VERSION} else 1)"
            ),
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _launcher_dependencies_ready(project_root: Path, python_bin: Path) -> bool:
    command = [
        str(python_bin),
        "-c",
        (
            "import os, sys; "
            "sys.path.insert(0, os.path.join(os.getcwd(), 'src')); "
            "from occams_beard.launcher import _load_web_dependencies; "
            "_load_web_dependencies()"
        ),
    ]
    result = subprocess.run(
        command,
        cwd=project_root,
        env=_build_runtime_environment(project_root),
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def _bootstrap_local_environment(project_root: Path, python_bin: Path) -> None:
    subprocess.run([str(python_bin), "-m", "venv", ".venv"], cwd=project_root, check=True)
    project_python = _resolve_project_python(project_root)
    subprocess.run(
        [str(project_python), "-m", "pip", "install", "--upgrade", "pip"],
        cwd=project_root,
        check=True,
    )
    subprocess.run(
        [str(project_python), "-m", "pip", "install", "-e", str(project_root)],
        cwd=project_root,
        check=True,
    )


def _build_runtime_environment(project_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(project_root / "src")
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _prepend_pythonpath(src_path, current_pythonpath)
    return env


def _prepend_pythonpath(src_path: str, current_pythonpath: str) -> str:
    if not current_pythonpath:
        return src_path

    segments = current_pythonpath.split(os.pathsep)
    if src_path in segments:
        return current_pythonpath
    return os.pathsep.join([src_path, current_pythonpath])


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


if __name__ == "__main__":
    raise SystemExit(main())
