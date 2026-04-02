# Platform Notes

Endpoint Diagnostics Lab targets macOS, Linux, and Windows with a standard-library-first approach. Cross-platform diagnostics at the host and network layer always involve tradeoffs, so this document makes those explicit.

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

Tradeoffs:
- Linux networking command output varies by distribution and age.
- Containerized or restricted environments may expose incomplete route or interface data.

## macOS

Primary sources:
- `sysctl`
- `vm_stat`
- `ifconfig`
- `netstat -rn`
- `scutil --dns`
- `df -kP`

Tradeoffs:
- Memory pressure is approximated from free, inactive, and speculative pages rather than using proprietary pressure metrics.
- macOS interface names such as `utun*` are useful for tunnel heuristics but are still not proof of an active VPN session.
- Some sandboxed or privacy-restricted execution contexts can return partial uptime or resolver data even when the host itself is healthy.

## Windows

Primary sources:
- PowerShell CIM queries
- `ipconfig /all`
- `route print`
- DNS server enumeration through PowerShell

Tradeoffs:
- Windows command availability and output formatting can vary more than Unix-like platforms.
- PowerShell is assumed for richer host data; if it is unavailable, the tool falls back to partial data and warnings.
- Localized output may require broader fixture coverage in future iterations.

## Connectivity Checks

TCP:
- uses direct `socket.create_connection`
- does not require shelling out for the core reachability signal
- supports operator-supplied targets from CLI arguments or a JSON target file

Ping:
- optional
- depends on `ping` availability and network policy

Traceroute:
- optional
- depends on `traceroute` or `tracert`
- partial or failed results are still useful evidence and should not be over-interpreted

## VPN Detection

VPN detection is intentionally heuristic. The current release uses:
- interface name patterns
- route-default interface hints

It does not claim certainty from those facts alone. That is a deliberate design choice to avoid overstating conclusions.

## Security Considerations

- No secrets are required for baseline operation.
- No privileged operations are requested automatically.
- Debug logging should be used carefully in shared environments because command invocation context can still be operationally sensitive.

## Performance Notes

- Commands are short-lived and timeout-bounded.
- Collection is synchronous and predictable for a CLI-first workflow.
- The first release favors simplicity and auditability over aggressive parallelism.
