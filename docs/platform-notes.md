# Platform Notes

Occam's Beard targets macOS, Linux, and Windows with a standard-library-first approach. Cross-platform diagnostics at the host and network layer always involve tradeoffs, so this document makes those explicit.

## Common Principles

- Baseline functionality should work without elevated privileges.
- Command execution should be bounded with timeouts.
- Missing commands should degrade into warnings, not silent failure.
- Platform differences should be normalized into stable models before findings run.

## Linux

Primary sources:
- `/proc/uptime`
- `/proc/meminfo`
- `ip addr show`
- `ip route show`
- `/etc/resolv.conf`
- `df -kP`

Fallbacks:
- `ifconfig`
- `netstat -rn`
- `arp -a` when `ip neigh show` is unavailable

Tradeoffs:
- Linux networking command output varies by distribution and age.
- Containerized or restricted environments may expose incomplete route or interface data.
- Neighbor-cache output can be stale or sparse, so ARP evidence is collected as supplemental context only.
- `traceroute` may be absent even when baseline TCP checks work; the tool warns instead of failing the run.

## macOS

Primary sources:
- `sysctl`
- `vm_stat`
- `ifconfig`
- `route -n get default`
- `netstat -rn`
- `scutil --dns`
- `df -kP`

Tradeoffs:
- Memory pressure is approximated from free, inactive, and speculative pages rather than using proprietary pressure metrics.
- macOS interface names such as `utun*` are useful for tunnel heuristics but are still not proof of an active VPN session.
- `route -n get default` is used to sharpen default-gateway detection, while `netstat -rn` remains the broader route-table source.
- Storage collection intentionally ignores pseudo-filesystem mounts such as `/dev` and CoreSimulator device volumes because they can report misleading capacity states that do not reflect host disk exhaustion.
- Some sandboxed or privacy-restricted execution contexts can return partial uptime or resolver data even when the host itself is healthy.
- `ping` and `traceroute` flags differ from Linux, so the collector uses macOS-specific argument sets and still treats those checks as optional.

## Windows

Primary sources:
- PowerShell CIM queries
- `ipconfig /all`
- `route print`
- `arp -a`
- DNS server enumeration through PowerShell

Tradeoffs:
- Windows command availability and output formatting can vary more than Unix-like platforms.
- PowerShell is assumed for richer host data; if it is unavailable, the tool falls back to partial data and warnings.
- Parser coverage includes common `ipconfig`, `route print`, and `tracert` formatting variants, including degraded and partially incomplete outputs.
- Full localization support is still not claimed. If output departs too far from the covered patterns, the tool prefers warnings and conservative route-state observations over guessing.
- `tracert` and `ping` use Windows-specific timeout semantics, so their output remains best-effort rather than authoritative.

## Connectivity Checks

TCP:
- uses direct `socket.create_connection`
- does not require shelling out for the core reachability signal
- supports operator-supplied targets from CLI arguments or a JSON target file

Ping:
- optional
- depends on `ping` availability and network policy
- uses platform-specific arguments rather than assuming Linux flags on every Unix-like host

Traceroute:
- optional
- depends on `traceroute` or `tracert`
- prefers numeric hop output where supported to reduce parser ambiguity
- distinguishes target reached, partial progress, command failure, and unavailable-command cases
- partial or failed results are still useful evidence and should not be over-interpreted

## VPN Detection

VPN detection is intentionally heuristic. The current release uses:
- interface name patterns
- usable-address presence on tunnel-like interfaces
- route-default interface hints

It does not claim certainty from those facts alone. That is a deliberate design choice to avoid overstating conclusions.

Some collector heuristics were refined using patterns from an earlier personal troubleshooting script, but the implementation here was rebuilt to fit the project’s structured architecture and evidence model.

## Security Considerations

- No secrets are required for baseline operation.
- No privileged operations are requested automatically.
- ARP data is summarized rather than dumped wholesale to reduce unnecessary exposure of local peer details in reports.
- Debug logging should be used carefully in shared environments because command invocation context can still be operationally sensitive.

## Performance Notes

- Commands are short-lived and timeout-bounded.
- Collection is synchronous and predictable for a CLI-first workflow.
- The first release favors simplicity and auditability over aggressive parallelism.
- Connectivity collectors remain synchronous so timeout behavior is predictable and easy to reason about in operator workflows.
- Dedicated MTU probing is intentionally omitted; the report surfaces existing per-interface MTU facts instead of adding a noisier active test.
