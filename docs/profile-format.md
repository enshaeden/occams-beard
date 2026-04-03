# Profile Format

## Purpose

Profiles provide reusable local issue scenarios without introducing a config service.

Use the optional `./profiles/` directory when you need to override or extend the built-in package profiles on a specific working copy or host.

## Discovery Order

Profiles are loaded from:

1. built-in package profiles under `src/occams_beard/profiles/`
2. optional local override directory `./profiles/`
3. optional override directory from `OCCAMS_BEARD_PROFILE_DIR`

Later files override earlier profiles by `id`.

This combined catalog is what `occams-beard run --list-profiles` and the support-path profile selector display.

## Validation Behavior

- Built-in profiles are strict. A malformed built-in profile is a repository defect and still fails loading.
- Optional profiles from `./profiles/` and `OCCAMS_BEARD_PROFILE_DIR` are soft-fail. Invalid files are skipped, and the CLI profile listing plus the support-path profile picker surface the skipped file path and validation reason.
- If an optional override is skipped, the earlier valid profile with the same `id` remains active.

## File Format

Profiles use TOML and support these fields:

- `id`: stable identifier
- `name`: operator-facing name
- `description`: short purpose statement
- `issue_category`: plain-language category
- `recommended_checks`: list of diagnostic domains
- `dns_hosts`: optional list of DNS hostnames
- `labels`: optional tags
- `safe_user_guidance`: optional operator-safe next steps
- `escalation_guidance`: optional escalation cues
- `[[tcp_targets]]`: optional repeated target blocks with:
  - `host`
  - `port`
  - `label`

## Example

```toml
id = "dns-issue"
name = "DNS Issue"
description = "Focused profile for name-resolution problems."
issue_category = "DNS issue"
recommended_checks = ["network", "routing", "dns", "connectivity"]
dns_hosts = ["github.com", "python.org", "pypi.org"]

[[tcp_targets]]
host = "1.1.1.1"
port = 53
label = "cloudflare-dns"
```

## Merge Behavior

- Explicit CLI or web check selections override profile `recommended_checks`.
- Explicit DNS hosts override profile DNS defaults.
- Explicit TCP targets and target files override profile TCP defaults.
- If no profile defaults exist for a relevant category, the global defaults remain in effect.
