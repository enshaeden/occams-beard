# Support Workflow

## Purpose

This workflow turns a local diagnostics run into a support-ready handoff without requiring a cloud dependency.

## Standard Flow

1. Start in one of two local paths:
   - `Check My Device` for a symptom-led safe run
   - `Work With Support` for a technician-directed plan
2. If support is involved, choose the closest local support profile and confirm the deeper probes or capture options that were requested.
3. Run diagnostics locally and watch the per-domain progress page until the results view is ready.
4. Review the results in this order:
   - what we know
   - what likely happened
   - what you can do now
   - when to contact support
   - what remains uncertain
5. Export a support bundle with the appropriate redaction level.

## Bundle Contents

- `result.json`: schema-versioned machine-readable result.
- `report.txt`: human-readable report from the same result object.
- `manifest.json`: bundle metadata, format version, file hashes, and redaction level.
- `redaction-report.txt`: what was redacted and why.
- `raw-commands.json`: optional and only present when raw capture was explicitly enabled.

Canonical committed examples live under [`sample_output/support-bundle-safe/`](../sample_output/support-bundle-safe/).
That example intentionally omits `raw-commands.json` because raw command capture is not exported unless the operator explicitly enables it for the bundle.

Use [`docs/result-schema.md`](result-schema.md) for the result contract and [`docs/privacy-and-threat-model.md`](privacy-and-threat-model.md) for redaction and sensitive-data handling.

Validate the exported bundle before handing it off when you need a trust check on local files:

```bash
python -m occams_beard.bundle_validator PATH
```

The validator checks the manifest, listed files, hashes, sizes, raw-capture presence, and schema-version consistency.

## Recommended Redaction Use

- `safe`: default for most helpdesk handoffs.
- `strict`: use when the bundle may leave the local admin boundary.
- `none`: local engineering use only when sensitive data exposure is acceptable.

## Escalation Guidance

- A self-serve run can continue into the guided-support path without discarding the earlier result.
- Escalate when the guided summary explicitly calls for helpdesk or admin involvement.
- Escalate when the run remains inconclusive after collecting the minimum relevant domains.
- Escalate before collecting privileged or policy-sensitive evidence not already covered by the tool.
