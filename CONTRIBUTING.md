# Contributing

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Development Commands

Run the unit suite:

```bash
PYTHONPATH=src:tests .venv/bin/python -m unittest discover -s tests -v
```

Run static analysis locally:

```bash
.venv/bin/ruff check src tests scripts
.venv/bin/mypy src tests/support.py scripts/refresh_sample_output.py scripts/live_smoke_validate.py
```

Check documentation and repository hygiene:

```bash
python scripts/check_docs.py
```

Refresh canonical sample artifacts:

```bash
.venv/bin/python scripts/refresh_sample_output.py
```

Validate a support bundle locally:

```bash
.venv/bin/python -m occams_beard.bundle_validator sample_output/support-bundle-safe
```

Run bounded live smoke validation on the current host:

```bash
.venv/bin/python scripts/live_smoke_validate.py --json-out live-smoke-summary.json
```

## Current CI Scope

Verified against the current project automation, the blocking CI path currently includes:

- documentation structure must pass
- unit tests must pass
- `ruff` must pass for `src`, `tests`, and `scripts`
- `mypy` must pass for `src`, `tests/support.py`, `scripts/refresh_sample_output.py`, and `scripts/live_smoke_validate.py`
- live smoke validation must pass on the GitHub-hosted Ubuntu, macOS, and Windows runners

`ruff` `E501` and the staged `mypy` target are part of the blocking path.

When this scope changes, update [README.md](README.md) and [CONTRIBUTING.md](CONTRIBUTING.md) in the same change.

## Documentation Policy

- Update an existing canonical document before creating a new one.
- Root markdown is restricted to `README.md`, `CHANGELOG.md`, and `CONTRIBUTING.md`.
- Durable reference docs belong under `docs/`. Architecture rationale belongs under `architecture/`.
- Keep one topic in one canonical home and add that document to the README documentation map.
- Delete absorbed docs instead of archiving them unless they still have distinct ongoing value.
- Delete run-specific assessment docs once their durable content has been absorbed into canonical docs.
- Do not commit transient planning, audit, or implementation-pass markdown as permanent repo documentation.

## Repository Hygiene

- Do not commit generated packaging output or duplicate package trees.
- `build/`, `dist/`, wheels, sdists, and any tracked `occams_beard` package tree
  outside `src/` are treated as generated artifacts.
- `python scripts/check_docs.py` enforces both the documentation rules above and
  the tracked-artifact hygiene guard.

## Contribution Rules

- Keep the shared runner central.
- Keep platform parsing out of findings.
- Keep UI concerns out of collectors.
- Prefer additive, reversible changes over rewrites.
- Add tests for new schema, bundle, profile, or UI behavior.
- If a change affects support artifacts, update the matching canonical docs under `docs/` and the README documentation map.
- Run `python scripts/check_docs.py` when adding, moving, or deleting markdown files.

## Intake Architecture Guardrails

- Keep self-serve intake logic centralized in `src/occams_beard/intake/` and `src/occams_beard/web/forms.py`.
- Treat `src/occams_beard/web/presentation/catalog.py` as presentation-only. It must not contain symptom-to-intent, intent-to-domain, or validation policy logic.
- Keep Flask route handlers in `src/occams_beard/web/routes.py` orchestration-only; do not add intake mapping or fallback policy branching there.
- Add or adjust symptom wording in the intake contract (`src/occams_beard/intake/catalog.py`) and keep deterministic resolution rules in `src/occams_beard/intake/resolver.py`.
- Add clarification behavior in `src/occams_beard/intake/clarification.py`, domain mapping behavior in `src/occams_beard/intake/domain_mapper.py`, and safety validation in `src/occams_beard/intake/validator.py`.
- Add or update regression coverage in `tests/test_app.py`, `tests/test_intake_resolver.py`, `tests/test_intake_domain_mapper.py`, and `tests/test_intake_validator.py` whenever intake behavior changes.
