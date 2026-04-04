# Occam's Beard

Occam's Beard is a local-first endpoint diagnostics proof of concept for cases
where a user can report "the network is broken," but support still needs
trustworthy evidence before acting. It collects bounded local facts, normalizes
them into stable models, evaluates deterministic findings, and renders the same
result through a CLI, a localhost web UI, text reports, and support bundles.

That problem matters operationally because endpoint incidents often fail at the
handoff boundary. Desktop support, systems administration, and network
operations may all touch the same case, yet the first evidence packet is often
assembled from screenshots, ad hoc commands, and inconsistent interpretation.
This repository explores a narrower and more useful question: how to capture
local evidence deterministically, reason over it without a black box, and hand
the result to the next support tier in a form that is reviewable and safe to
share.

The design choices are deliberate. Collection stays local and read-mostly.
Findings are the source of truth and are evaluated only from collected evidence.
The explanation layer stays subordinate to those findings. CLI, web, launcher,
JSON output, and support-bundle export all share one runner and one result
model. As a portfolio artifact, the repository is meant to show systems
engineering judgment in diagnostics architecture, operational scope control,
support handoff design, and privacy-aware local tooling.

## Why this repo matters

This repo is evidence of how the author approaches endpoint tooling as a
systems and operations problem rather than as a UI exercise or a convenience
script. It shows an emphasis on deterministic evidence evaluation, explicit
architectural boundaries, reusable result contracts, privacy-aware artifact
generation, and support workflows that survive escalation. It also shows
restraint: the implementation stays local-first, avoids agent or fleet
pretensions, and keeps explanation bounded to what the system can actually
justify from collected facts.

## Representative failure classes

The current system is designed to help isolate several common endpoint and
access-path failure classes, including:

- local interface misconfiguration, such as an active interface without a
  usable local address
- default route inconsistency, including missing or suspect default-path state
- DNS failure with raw IP reachability, which points toward resolver-path
  issues rather than total network loss
- selective service reachability failure, where general connectivity works but
  a configured service path does not
- VPN path failure or tunnel-related misrouting
- local resource or hardware degradation, including host pressure, storage
  exhaustion, battery health warnings, and storage-device health states exposed
  by the operating system

These are representative classes, not a claim of exhaustive diagnosis.

## Design overview

Occam's Beard follows one shared execution path:

```text
CLI / Web / Launcher / Support Bundle Export
  -> build_run_options
  -> shared runner
  -> collectors
  -> normalized models
  -> deterministic findings
  -> execution status + deterministic explanation
  -> JSON / report / support bundle / HTML
```

The core layers are intentionally separated:

- `collectors/` gathers raw endpoint evidence
- `models.py` defines normalized facts, findings, execution records, guided
  summaries, and support-bundle metadata
- `findings.py` evaluates deterministic rules over normalized facts
- `execution.py` records per-domain and per-probe status
- `explanations.py` derives bounded plain-language guidance from findings
- `serializers.py`, `report.py`, and `support_bundle.py` render the same result
  object for different consumers
- `bundle_validator.py` verifies support-bundle manifests, hashes, and schema
  consistency
- `web/` keeps route composition, form parsing, progress shaping, and result
  presentation above the shared result model
- `cli.py`, `app.py`, and `launcher.py` stay thin over the same runner

The runtime remains standard-library-first apart from Flask, which is the only
runtime dependency and exists to serve the local web interface.

## Operational boundaries

This repository is intentionally narrow in scope.

- It is local-first and on-device by default.
- It is read-mostly diagnostics, not remediation.
- It is not a resident agent, daemon, RMM, or fleet control plane.
- It is not a cloud-dependent service and includes no built-in upload path.
- It is not an open-ended AI assistant or a black-box diagnosis engine.
- It does not replace human support judgment. It produces evidence, findings,
  and support-ready outputs that make that judgment easier.

## Interfaces and outputs

The same runner powers three operator surfaces:

- `occams-beard run` for direct CLI use
- `occams-beard-web` for a localhost Flask UI
- `occams-beard-operator` for the local launcher workflow

The web UI begins with two explicit paths:

1. `Check My Device` for symptom-led self-service with a safe default plan
2. `Work With Support` for technician-directed runs, deeper probes, and
   support-bundle handoff

Both paths converge on the same result object, which is then rendered as:

- schema-versioned `result.json`
- a human-readable `report.txt`
- a local support bundle with manifest, redaction report, and optional raw
  command capture
- a server-rendered HTML results view

Reusable issue scenarios are file-backed through local profiles under
[`src/occams_beard/profiles/`](src/occams_beard/profiles/), which keeps guided
support flows repeatable without introducing a remote configuration service.

## Usage

Setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Windows setup:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Run the default suite:

```bash
occams-beard run
```

List available profiles:

```bash
occams-beard run --list-profiles
```

Run a profile:

```bash
occams-beard run --profile no-internet
```

Export schema-versioned JSON:

```bash
occams-beard run --json-out result.json
```

Export a redacted support bundle:

```bash
occams-beard run --profile vpn-issue --support-bundle bundle.zip --redaction-level safe
```

Opt in to raw command capture for the support bundle:

```bash
occams-beard run --support-bundle bundle.zip --bundle-include-raw
```

Load TCP targets from the example input file:

```bash
occams-beard run --target-file sample_output/example-targets.json
```

Validate an existing support bundle:

```bash
occams-beard-validate-bundle bundle.zip
```

Run the localhost web UI:

```bash
occams-beard-web
```

Run the local launcher:

```bash
occams-beard-operator
```

On macOS, you can also double-click
[`Open Device Check.command`](<Open Device Check.command>) from the repo root.
It starts the local interface without leaving a Terminal window on screen and
stops the local server after the browser page is closed.

On Windows, use [`Open Device Check.cmd`](<Open Device Check.cmd>) from the
repo root. The root `.command` and `.cmd` files delegate to the same shared
Python bootstrap so the environment bootstrap and operator launch behavior stay
aligned across platforms, while the macOS wrapper retains its Terminal-hiding
behavior.

## Support-ready artifacts

Support bundles are a primary output, not an afterthought. They remain local
and file-based and can include:

- `result.json`
- `report.txt`
- `manifest.json`
- `redaction-report.txt`
- `raw-commands.json` when raw capture was explicitly enabled

Bundle export keeps privacy controls visible to the operator. Redaction levels
are explicit, raw command capture is opt-in, and raw capture is excluded from
`result.json`. The standalone validator can verify a directory or zip export
before handoff by checking manifest presence, listed files, sizes, hashes,
raw-capture consistency, and schema-version agreement between `manifest.json`
and `result.json`.

See [`docs/support-workflow.md`](docs/support-workflow.md),
[`docs/privacy-and-threat-model.md`](docs/privacy-and-threat-model.md), and
[`docs/result-schema.md`](docs/result-schema.md).

## Proof, not promises

What this repository demonstrates today is concrete:

- local-first diagnostics that run on the endpoint and keep artifacts on local
  storage
- deterministic findings over normalized facts
- one shared runner across CLI, web, launcher, and export surfaces
- schema-versioned machine-readable output
- support-bundle export with validation and visible redaction controls
- guided summaries that are derived from findings rather than acting as a
  separate reasoning engine
- cross-platform parsing and regression coverage for supported Linux, macOS,
  and Windows collection paths represented in the repository

What it does not claim is equally important:

- no production deployment, enterprise adoption, or measured operational impact
- no cloud service, remote collection path, or persistent multi-user platform
- no agent, daemon, dashboard, or fleet-management behavior
- no automatic remediation
- no guarantee that every OS version, localization variant, enterprise image,
  or assistive-technology path has been validated

Remaining gaps and next steps are tracked in
[`docs/roadmap.md`](docs/roadmap.md). Current work there includes broader
fixture coverage, more real-world platform variants, additional redaction
verification, and manual assistive-technology validation.

For incident-oriented walkthroughs of supported failure classes, see
[`docs/case-studies.md`](docs/case-studies.md).

## Documentation map

- [`CONTRIBUTING.md`](CONTRIBUTING.md): setup, contribution rules, and
  documentation policy
- [`CHANGELOG.md`](CHANGELOG.md): unreleased and released changes
- [`architecture/decisions.md`](architecture/decisions.md): architecture
  rationale and non-goals
- [`docs/case-studies.md`](docs/case-studies.md): representative
  incident-style walkthroughs grounded in committed deterministic artifacts
- [`docs/diagnostic-model.md`](docs/diagnostic-model.md): execution flow and
  model boundaries
- [`docs/finding-rules.md`](docs/finding-rules.md): deterministic findings
  boundary and finding output
- [`docs/result-schema.md`](docs/result-schema.md): machine-readable result
  contract
- [`docs/profile-format.md`](docs/profile-format.md): local profile format
- [`docs/privacy-and-threat-model.md`](docs/privacy-and-threat-model.md):
  privacy and redaction posture
- [`docs/platform-notes.md`](docs/platform-notes.md): platform-specific
  collection notes
- [`docs/support-workflow.md`](docs/support-workflow.md): support-ready handoff
  and bundle export flow
- [`docs/roadmap.md`](docs/roadmap.md): current posture, blockers, and next
  milestones
- [`docs/ACCESSIBILITY_NOTES.md`](docs/ACCESSIBILITY_NOTES.md): completed UI
  accessibility work and remaining validation gaps

## Development

Run tests:

```bash
PYTHONPATH=src:tests .venv/bin/python -m unittest discover -s tests -v
```

Static analysis:

```bash
.venv/bin/ruff check src tests scripts
.venv/bin/mypy src tests/support.py scripts/refresh_sample_output.py scripts/live_smoke_validate.py
```

Check documentation structure:

```bash
python3 scripts/check_docs.py
```

Refresh canonical sample artifacts:

```bash
.venv/bin/python scripts/refresh_sample_output.py
```

Run bounded live smoke validation on the current host:

```bash
.venv/bin/python scripts/live_smoke_validate.py --json-out live-smoke-summary.json
```

Validate a committed or operator-supplied support bundle:

```bash
.venv/bin/python -m occams_beard.bundle_validator sample_output/support-bundle-safe
```

CI blocks on documentation structure, unit tests, `ruff`, `mypy`, and bounded
live smoke validation on GitHub-hosted Ubuntu, macOS, and Windows runners.
Committed artifacts under [`sample_output/`](sample_output/) are deterministic
review fixtures generated from the current code. They are useful for contract
review and regression testing, but they are not live captures from a production
endpoint.
