#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_DOC_ALLOWLIST = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md"}
BANNED_ROOT_DOCS = {
    "CURRENT_STATE.md",
    "GAP_ANALYSIS.md",
    "PRODUCT_TARGET.md",
    "PRODUCTION_PLAN.md",
    "SUPPORT_WORKFLOW.md",
}
DOC_INDEX = REPO_ROOT / "README.md"
DOCUMENTATION_DIRECTORIES = (REPO_ROOT / "docs", REPO_ROOT / "architecture")
OPTIONAL_MARKDOWN_DIRECTORIES = (
    REPO_ROOT / "sample_output",
    REPO_ROOT / "profiles",
)
BANNED_MARKDOWN_PATHS = {
    REPO_ROOT / "docs" / "NEXT_STAGE_ASSESSMENT.md": (
        "Run-specific assessment docs must be absorbed into canonical docs."
    ),
    REPO_ROOT / "docs" / "STATIC_ANALYSIS_BACKLOG.md": (
        "Static-analysis scope belongs in the canonical development docs."
    ),
    REPO_ROOT / "profiles" / "README.md": (
        "Profile override guidance belongs in docs/profile-format.md."
    ),
    REPO_ROOT / "sample_output" / "README.md": (
        "Sample artifact guidance belongs in docs/result-schema.md."
    ),
}
LINK_PATTERN = re.compile(r"!?\[[^\]]+\]\(([^)]+)\)")
GENERATED_ARTIFACT_ROOTS = ("build", "dist")
PRIMARY_PACKAGE_ROOT = PurePosixPath("src/occams_beard")


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def iter_markdown_files() -> list[Path]:
    markdown_files = set(REPO_ROOT.glob("*.md"))
    for directory in DOCUMENTATION_DIRECTORIES + OPTIONAL_MARKDOWN_DIRECTORIES:
        if directory.exists():
            markdown_files.update(directory.rglob("*.md"))
    return sorted(markdown_files)


def extract_relative_link_targets(source: Path) -> list[str]:
    targets: list[str] = []
    text = source.read_text(encoding="utf-8")
    for raw_target in LINK_PATTERN.findall(text):
        target = raw_target.strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        target = target.split("#", 1)[0].strip()
        if not target:
            continue
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if target.startswith("#"):
            continue
        targets.append(target)
    return targets


def resolve_link(source: Path, target: str) -> Path:
    if target.startswith("/"):
        return (REPO_ROOT / target.lstrip("/")).resolve()
    return (source.parent / target).resolve()


def preview_paths(paths: list[str], *, limit: int = 5) -> str:
    preview = paths[:limit]
    suffix = " ..." if len(paths) > limit else ""
    return ", ".join(preview) + suffix


def tracked_repo_paths(errors: list[str]) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        errors.append(f"Unable to enumerate tracked files for repo hygiene checks: {exc}")
        return set()

    tracked_paths: set[str] = set()
    for path in result.stdout.split(b"\0"):
        if not path:
            continue
        relative_path = path.decode("utf-8")
        if (REPO_ROOT / relative_path).exists():
            tracked_paths.add(relative_path)
    return tracked_paths


def is_under_root(relative_path: str, root_name: str) -> bool:
    return relative_path == root_name or relative_path.startswith(f"{root_name}/")


def duplicate_package_roots(tracked_paths: set[str]) -> list[str]:
    duplicates: set[str] = set()
    for relative_path in tracked_paths:
        path = PurePosixPath(relative_path)
        if "occams_beard" not in path.parts:
            continue
        package_index = path.parts.index("occams_beard")
        package_root = PurePosixPath(*path.parts[: package_index + 1])
        if package_root != PRIMARY_PACKAGE_ROOT:
            duplicates.add(package_root.as_posix())
    return sorted(duplicates)


def check_root_markdown(errors: list[str]) -> None:
    root_markdown = {path.name for path in REPO_ROOT.glob("*.md")}
    extra = sorted(root_markdown - ROOT_DOC_ALLOWLIST)
    missing = sorted(ROOT_DOC_ALLOWLIST - root_markdown)
    banned = sorted(root_markdown & BANNED_ROOT_DOCS)

    if extra:
        errors.append("Unexpected root markdown files: " + ", ".join(extra))
    if missing:
        errors.append("Missing required root markdown files: " + ", ".join(missing))
    if banned:
        errors.append(
            "Banned transient root markdown files are still present: " + ", ".join(banned)
        )


def check_banned_markdown(errors: list[str]) -> None:
    for path, reason in BANNED_MARKDOWN_PATHS.items():
        if path.exists():
            errors.append(
                "Banned markdown file is still present: "
                f"{repo_relative(path)} ({reason})"
            )


def check_readme_documentation_map(errors: list[str]) -> None:
    readme_links: set[str] = set()
    for target in extract_relative_link_targets(DOC_INDEX):
        resolved = resolve_link(DOC_INDEX, target)
        if not resolved.exists() or resolved.suffix != ".md":
            continue
        try:
            relative = repo_relative(resolved)
        except ValueError:
            continue
        if relative.startswith("docs/") or relative.startswith("architecture/"):
            readme_links.add(relative)

    expected = sorted(
        repo_relative(path)
        for directory in DOCUMENTATION_DIRECTORIES
        for path in directory.rglob("*.md")
    )
    missing_links = [path for path in expected if path not in readme_links]
    if missing_links:
        errors.append("README documentation map is missing: " + ", ".join(missing_links))


def check_relative_links(errors: list[str]) -> None:
    for source in iter_markdown_files():
        for target in extract_relative_link_targets(source):
            resolved = resolve_link(source, target)
            if not resolved.exists():
                errors.append(f"{repo_relative(source)} has a broken relative link: {target}")


def check_repo_hygiene(errors: list[str], tracked_paths: set[str]) -> None:
    for artifact_root in GENERATED_ARTIFACT_ROOTS:
        tracked_artifacts = sorted(
            path for path in tracked_paths if is_under_root(path, artifact_root)
        )
        if tracked_artifacts:
            errors.append(
                f"Tracked generated artifacts are present under {artifact_root}/: "
                f"{preview_paths(tracked_artifacts)}"
            )

    duplicate_roots = duplicate_package_roots(tracked_paths)
    if duplicate_roots:
        errors.append(
            "Duplicate tracked occams_beard package tree outside src/: "
            + ", ".join(duplicate_roots)
        )

    tracked_generated_python = sorted(
        path
        for path in tracked_paths
        if path.endswith(".py")
        and any(is_under_root(path, root_name) for root_name in GENERATED_ARTIFACT_ROOTS)
    )
    if tracked_generated_python:
        errors.append(
            "Tracked Python files were found in generated artifact directories: "
            + preview_paths(tracked_generated_python)
        )


def main() -> int:
    errors: list[str] = []
    tracked_paths = tracked_repo_paths(errors)
    check_root_markdown(errors)
    check_banned_markdown(errors)
    check_readme_documentation_map(errors)
    check_relative_links(errors)
    check_repo_hygiene(errors, tracked_paths)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Documentation and repository hygiene checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
