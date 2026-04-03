# Diagnostic Model

## Design

Occam's Beard still follows the same execution flow:

```text
CLI / Web
  -> build_run_options
  -> shared runner
  -> collectors
  -> normalized models
  -> deterministic findings
  -> execution status + guided summary
  -> JSON / report / support bundle / HTML
```

## Model Boundaries

- Collectors gather facts and warnings.
- `models.py` defines normalized facts, findings, execution records, guided summaries, and support-bundle metadata.
- `findings.py` evaluates deterministic rules only from collected evidence.
- `execution.py` turns the completed run into per-domain and per-probe execution status.
- `assistant.py` adds deterministic plain-language guidance on top of findings.
- `serializers.py`, `report.py`, and `support_bundle.py` render the same result object for different consumers.

## Current Capabilities

- shared runner for CLI and web
- schema-versioned `result.json`
- execution status values for `passed`, `failed`, `partial`, `unsupported`, `skipped`, and `not_run`
- additive battery and storage-device health facts under the existing `resources` and `storage` domains
- local profile defaults for repeatable issue scenarios
- support-bundle export with optional raw command capture
- standalone support-bundle validation against the current manifest format

## Constraints

- platform parsing stays below findings
- hardware facts stay additive under `resources` and `storage`; there is no new top-level hardware domain
- UI stays above the result model
- support artifacts remain local
- no automatic remediation is introduced
