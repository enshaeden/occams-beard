# Result Schema

## Schema Version

Current result schema: `1.4.0`

This schema version is separate from the application version. The application can change without changing the result schema, and the result schema can change even if the operator-facing UI stays similar.

## Top-Level Shape

`result.json` includes:

- `schema_version`
- `metadata`
- `platform`
- `facts`
- `findings`
- `probable_fault_domain`
- `warnings`
- `execution`
- `guided_experience`

Raw command capture is intentionally excluded from `result.json`. If enabled, it lives only in the support bundle as `raw-commands.json`.
The bounded process-snapshot commands used for host-pressure hints are also excluded from raw-command capture so support bundles do not accidentally turn the feature into a process inventory export.

`guided_experience` is a deterministic explanation surface derived from findings and execution state. It is not an independent reasoning engine and should not contradict or bypass `findings`.

## Additive `1.4.0` Fields

Schema `1.4.0` adds optional host-pressure, storage-pressure, and clock-state fields:

- Under `facts.resources`:
  - `battery`: read-only battery state when the endpoint exposes it
  - `storage_devices`: read-only storage-device health records when the endpoint exposes them
  - `cpu.load_ratio_1m` and `cpu.saturation_level`: logical-core saturation hints derived from the current load snapshot
  - `memory.available_percent`, optional swap fields, and optional commit-pressure fields: snapshot-only local memory pressure evidence when the platform exposes it
  - `process_snapshot`: bounded process-load category summaries derived from one local snapshot, not a persistent process inventory
- Under `facts.resources.disks[*]`:
  - `free_percent`: operator-friendly free-space percentage for the current filesystem snapshot
  - `pressure_level`: deterministic storage-pressure classification for that volume: `critical`, `low`, `normal`, or `unknown`
  - `role_hint`: coarse operational role for the monitored volume, used only to explain likely impact areas such as system writes or user-data writes
- Under `facts.time`:
  - `local_time_iso` and `utc_time_iso`: the current local and UTC clock snapshot captured on the endpoint
  - `timezone_name`, optional `timezone_identifier`, and optional `timezone_identifier_source`: bounded local timezone state when the platform exposes it
  - `utc_offset_minutes` and optional `timezone_offset_consistent`: current offset facts and a bounded consistency check when an IANA timezone identifier is available
  - `skew_check`: a one-shot bounded external reference comparison with `status`, reference metadata, optional measured skew, and explicit failure details when the operator enabled it

These fields are additive. Existing consumers that ignore unknown fields can continue to parse the rest of the result.
The new fields remain read-only and snapshot-only. They do not represent background sampling, time synchronization, destructive testing, vendor-specific SMART parsing sprawl, or long-term baselines.

## Execution Status Model

Each `execution` record includes:

- `domain`
- `label`
- `status`
- `selected`
- `duration_ms`
- `summary`
- `warnings`
- `probes`
- `creates_network_egress`

Supported status values:

- `passed`
- `failed`
- `partial`
- `unsupported`
- `skipped`
- `not_run`

### Status semantics

- `passed`: the domain or probe completed successfully.
- `failed`: the domain or probe ran and the tested path failed.
- `partial`: the domain ran but returned mixed, degraded, or incomplete coverage.
- `unsupported`: the probe or domain could not run on this endpoint or with the available tools.
- `skipped`: the probe was intentionally not run, for example optional ping or trace when not enabled.
- `not_run`: the domain was not selected for the run.

## Compatibility Assumptions

- Pre-schema-versioned JSON artifacts are historical and should be treated as unversioned review fixtures.
- Schema `1.0.0` is the first explicit compatibility point.
- Schema `1.1.0` remains a prior compatibility point.
- Schema `1.2.0` remains a prior compatibility point.
- Schema `1.3.0` remains a prior compatibility point.
- Schema `1.4.0` is the current compatibility point.
- Additive fields should not require a major schema bump.
- Renaming or removing fields should require a major schema bump.

## Support-Bundle Validation

The support-bundle format remains `1.0.0`. Validate a directory or zip bundle with:

```bash
python -m occams_beard.bundle_validator PATH
```

The validator checks manifest presence, listed files, sizes, hashes, raw-capture consistency, and `schema_version` agreement between `manifest.json` and `result.json`.

## Canonical Review Artifacts

Current committed examples live under [`sample_output/`](../sample_output/):

- [`sample_output/default-run/result.json`](../sample_output/default-run/result.json) and [`sample_output/default-run/report.txt`](../sample_output/default-run/report.txt): baseline full-suite example
- [`sample_output/profile-dns-issue/result.json`](../sample_output/profile-dns-issue/result.json) and [`sample_output/profile-dns-issue/report.txt`](../sample_output/profile-dns-issue/report.txt): profile-based DNS scenario
- [`sample_output/profile-vpn-issue/result.json`](../sample_output/profile-vpn-issue/result.json) and [`sample_output/profile-vpn-issue/report.txt`](../sample_output/profile-vpn-issue/report.txt): profile-based VPN and private-resource scenario
- [`sample_output/degraded-partial/result.json`](../sample_output/degraded-partial/result.json) and [`sample_output/degraded-partial/report.txt`](../sample_output/degraded-partial/report.txt): degraded mixed-result scenario
- [`sample_output/support-bundle-safe/manifest.json`](../sample_output/support-bundle-safe/manifest.json), [`sample_output/support-bundle-safe/result.json`](../sample_output/support-bundle-safe/result.json), [`sample_output/support-bundle-safe/report.txt`](../sample_output/support-bundle-safe/report.txt), and [`sample_output/support-bundle-safe/redaction-report.txt`](../sample_output/support-bundle-safe/redaction-report.txt): canonical safe-redaction support-bundle example

The support-bundle sample intentionally omits `raw-commands.json` because raw command capture is included only when the run collected it and the export explicitly requested it.

[`sample_output/example-targets.json`](../sample_output/example-targets.json) is the canonical example input file for `occams-beard run --target-file`.

Refresh the committed artifacts with:

```bash
.venv/bin/python scripts/refresh_sample_output.py
```

Regression coverage lives in [`tests/test_sample_output.py`](../tests/test_sample_output.py).

These are deterministic review fixtures generated from the current code. They are suitable for contract review and regression testing, but they are not live endpoint captures.
