# Support Workflow

## Purpose

This workflow turns a local diagnostics run into a support-ready handoff
without introducing a cloud dependency. Support bundles are a core product
surface, not an incidental export.

## Current Runtime Paths

### Check My Device

1. Select the symptom that best matches the issue.
2. Review the suggested self-serve plan.
3. If the resolved intent defines clarification, answer the current prompt so
   the plan can narrow scope before the run starts.
4. Run diagnostics locally and wait for the results view.
5. Review the result and either export a support bundle or continue into the
   support-directed path.

### Work With Support

1. Select the requested support profile.
2. Confirm or adjust the requested checks, targets, DNS hosts, optional probes,
   and raw-capture setting.
3. Run diagnostics locally and wait for the results view.
4. Review the result and export a support bundle with the required redaction
   level.

A self-serve run can bridge into `Work With Support` without discarding the
earlier result.

## Support Bundle Flow

1. Review the result while the condition is still present.
2. Choose the required redaction level.
3. Export the bundle locally.
4. Validate the exported directory or zip when you need a trust check before
   handoff.
5. Send the validated bundle through the support channel that already exists
   outside this repository.

Validate the exported bundle locally:

```bash
python -m occams_beard.bundle_validator PATH
```

The validator checks the manifest, listed files, hashes, sizes, raw-capture
presence, and schema-version consistency.

## Bundle Contents

- `result.json`: schema-versioned machine-readable result.
- `report.txt`: human-readable report generated from the same result object.
- `manifest.json`: bundle metadata, file hashes, file sizes, and redaction
  level.
- `redaction-report.txt`: what was redacted and why.
- `raw-commands.json`: optional and present only when raw capture was explicitly
  enabled.

Canonical committed examples live under
[`sample_output/support-bundle-safe/`](../sample_output/support-bundle-safe/).
That example intentionally omits `raw-commands.json` because raw command capture
is not exported unless the operator explicitly enables it.

Use [`docs/result-schema.md`](result-schema.md) for the result contract and
[`docs/privacy-and-threat-model.md`](privacy-and-threat-model.md) for redaction
and sensitive-data handling.

## Current Limitations

- Clarification is currently exposed on the self-serve web path only.
  `Work With Support` and the CLI remain explicit operator-selected flows.
- Self-serve clarification is intentionally minimal. The UI renders one pending
  question at a time, and the current contract is capped at two prompts per
  intent.
- Bundle handoff remains manual. There is no built-in upload path, remote
  collection path, or persistent support service behind bundle export.

## Boundaries

- Bundle export and validation stay local-first and file-based.
- Bundle mechanics remain subordinate to the diagnostics result model.
- Raw command capture is opt-in and excluded from `result.json`.
- The workflow does not introduce automatic remediation or unattended follow-up
  collection.

## Recommended Redaction Use

- `safe`: default for most helpdesk handoffs.
- `strict`: use when the bundle may leave the local admin boundary.
- `none`: local engineering use only when sensitive data exposure is
  acceptable.
