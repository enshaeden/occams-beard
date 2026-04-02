# Roadmap

## Current Release Focus

Version `0.1.0` is intentionally narrow:
- local CLI execution
- structured diagnostics collection
- deterministic findings
- machine-readable JSON
- concise operator reporting
- representative sample artifacts for GitHub review
- lightweight local formatting, lint, and type-check support
- representative tests and documentation

## Next Logical Improvements

### Near Term

- broaden parser fixture coverage for additional platform variants
- improve routing interpretation for split-tunnel and policy-route cases
- add optional saved raw command capture for offline troubleshooting bundles
- add a richer summary of degraded versus unsupported checks

### Medium Term

- add importable sample fixture packs for integration-style parser tests
- add constrained baseline checks for proxy visibility and captive portal hints
- support optional configuration files for repeatable service-target bundles

### Intentionally Deferred

- background agents or daemons
- dashboards or web frontends
- remote orchestration
- user accounts and RBAC
- automatic remediation
- cloud sync or centralized storage

## Change Safety and Rollback

This first release is fully additive. Rollback is straightforward:
- remove the `endpoint-diagnostics-lab/` project directory
- revert the introducing commit

No migrations, background services, or persistent system changes are performed, so rollback does not require endpoint cleanup.
