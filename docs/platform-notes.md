# Platform Notes

## What this is

This document records the platform-specific sources, assumptions, and degradation behavior behind Occam's Beard.

## Problem space

Cross-platform diagnostics require different operating system commands, data sources, and parsing rules. Treating those differences as incidental usually produces inconsistent output or stronger claims than the source data supports.

## Design approach

Occam's Beard uses a standard-library-first runtime and relies on built-in operating system facilities where needed. Baseline checks are designed to work without elevated privileges, command execution is bounded with timeouts, and missing tools degrade into warnings rather than silent skips.

Platform-specific collection is normalized before findings run. That keeps platform drift out of the reasoning layer and makes partial results explicit.

## Key capabilities

- Cross-platform collection for macOS, Linux, and Windows
- Platform-specific command selection with bounded execution
- Stable normalization for interfaces, routes, DNS state, connectivity, and warnings
- Best-effort optional ping and traceroute collection with platform-aware argument handling

## Architecture

Common rules:

- Baseline collection should succeed without `sudo` or administrator privileges.
- Missing commands should produce warnings.
- Optional probes should not block the rest of the run.
- Supplemental evidence such as ARP or neighbor data should remain contextual.

Primary sources by platform:

Linux:

- `/proc/uptime`
- `/proc/meminfo`
- `ip addr show`
- `ip route show`
- `/etc/resolv.conf`
- `df -kP`

macOS:

- `sysctl`
- `vm_stat`
- `ifconfig`
- `route -n get default`
- `netstat -rn`
- `scutil --dns`
- `df -kP`

Windows:

- PowerShell CIM queries
- `ipconfig /all`
- `route print`
- `arp -a`
- PowerShell DNS server enumeration

Connectivity sources:

- generic TCP checks use direct socket connections
- ping uses platform-specific `ping` semantics
- traceroute uses `traceroute` or `tracert` with platform-aware parsing

## Usage

Use this document when you need to understand why a platform returned partial data or why a probe was reported as degraded.

Examples:

```bash
occams-beard run --enable-ping --enable-trace
```

```bash
occams-beard run --checks network,routing,dns,connectivity
```

When the result includes warnings, compare them against the notes here before treating the absence of a detail as evidence of failure.

## Tradeoffs and limitations

Linux:

- command output varies by distribution and age
- restricted or containerized environments can expose incomplete route or interface data
- neighbor-cache output can be stale or sparse

macOS:

- memory pressure is approximated from available page-state data rather than proprietary metrics
- `utun*` and similar interfaces are useful tunnel signals but not proof of a working VPN session
- sandboxed or privacy-restricted contexts can return partial uptime or resolver data
- pseudo-filesystem mounts such as `/dev` and CoreSimulator volumes are excluded from host disk pressure evaluation

Windows:

- richer host data depends on broadly available PowerShell behavior
- output formatting varies more than on Unix-like platforms
- localized or older command variants may degrade into warnings or partial route observations

Shared limits:

- traceroute parsing is conservative and some outputs remain only partially parsed
- ping and traceroute availability depends on command presence and network policy
- VPN detection is heuristic and based on interface, address, and route signals rather than authoritative session state

## Future work

- Broaden fixture coverage for Windows and traceroute variants
- Add additional non-privileged fallback probes where sandboxed environments still return partial data
- Refine tunnel and route interpretation where it can remain conservative
