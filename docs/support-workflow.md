# Support Workflow

## Purpose

This workflow turns a local diagnostics run into a support-ready handoff without requiring a cloud dependency. Support bundles are a core product surface, not an incidental export.

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

This workflow exists to support only four product flows:

1. collect trustworthy local evidence
2. explain likely fault domains clearly
3. produce support-ready handoff artifacts
4. help a user or operator choose safe next steps

## Intake Clarification Expectations

Intake clarification is now modeled as a deterministic pre-execution step in the intake package (independent of Flask routes).

- Support-facing handoff should expect up to two clarification answers per resolved intent before execution scope is finalized.
- Clarification may resolve early to a pathway/domain focus, or fall back to a default pathway when answers remain uninformative.
- This phase only defines the engine and context model; web route flow remains the existing one-step submit model until later wiring phases.

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

## Boundaries

- Bundle export and validation stay local-first and file-based.
- There is no built-in upload path, remote collection path, or persistent service behind bundles.
- Bundle mechanics stay subordinate to the diagnostics result model; they are not a second platform inside the repo.

## Recommended Redaction Use

- `safe`: default for most helpdesk handoffs.
- `strict`: use when the bundle may leave the local admin boundary.
- `none`: local engineering use only when sensitive data exposure is acceptable.

## Bundle Export UI

The redaction-level selector in the support-bundle export form uses native radio
inputs wrapped by full-width selectable cards. This keeps the control
screen-reader and keyboard friendly while making the selected state obvious from
the card border, background tint, and focus ring instead of relying only on the
radio dot.

The implementation intentionally keeps native radio semantics so:

- the entire row is clickable through the associated label
- `Tab` moves focus into the group and arrow keys move between options
- assistive technology announces the group, option label, and selected state

## Escalation Guidance

- A self-serve run can continue into the guided-support path without discarding the earlier result.
- Escalate when the guided summary explicitly calls for helpdesk or admin involvement.
- Escalate when the run remains inconclusive after collecting the minimum relevant domains.
- Escalate before collecting privileged or policy-sensitive evidence not already covered by the tool.
