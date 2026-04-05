# Privacy and Threat Model

## Local-First Posture

Occam's Beard is local-first and on-device by default:

- diagnostics run on the local endpoint
- findings are derived locally
- support bundles are written to local files
- there is no built-in upload path

## Sensitive Data Categories

Potentially sensitive values include:

- current username
- endpoint hostname
- local timezone identifier
- DNS targets
- configured service targets
- local IP addresses
- route gateways and interface names
- ARP / neighbor data
- raw command stdout and stderr

## Raw Command Capture

- Raw command capture is opt-in.
- It is not included in `result.json`.
- It is only exported as `raw-commands.json` when explicitly requested and when the run was started with raw capture enabled.

## Redaction Levels

- `none`: no redaction.
- `safe`: redacts endpoint identifiers, hostnames, private addresses, and MAC addresses while preserving general structure.
- `strict`: redacts everything in `safe` plus public IPs, interface names, and target labels.

Free-text and raw-command redaction now applies a generic IP sweep after exact-value registration, so uncatalogued IPv4 and IPv6 addresses in text artifacts are still redacted when the selected level requires it.
Generic hostname redaction is still intentionally avoided; hostnames are redacted only when they were explicitly registered from collected facts.

Every bundle includes `redaction-report.txt` so the operator can see what level was used.

## Network Egress Disclosure

The following domains can create network egress:

- `dns`
- `connectivity`
- `services`
- `time` when the bounded clock-skew probe is explicitly enabled

Within `connectivity`, optional `ping` and `trace` probes also create network egress when enabled.
Within `time`, the default local clock snapshot stays on-device; only the optional skew probe creates network traffic.

## Threat Model Boundaries

The tool does not attempt to defend against:

- a fully compromised local host
- malicious kernel or OS command output
- hostile remote networks altering raw diagnostic responses

The tool does attempt to avoid accidental over-collection by:

- keeping collection local and read-mostly
- keeping raw capture explicit
- keeping redaction operator-visible
- keeping support artifacts local-only
