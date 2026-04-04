# Platform Notes

## General Rules

- Baseline collection remains non-privileged.
- Missing commands degrade into warnings or `unsupported` execution status instead of silent skips.
- Optional ping and traceroute remain best-effort.
- Raw command capture is opt-in and local only.
- Repo-root operator launch now uses platform-specific root shims that delegate to one shared Python bootstrap module; macOS keeps `Open Device Check.command`, and Windows uses `Open Device Check.cmd`.

## Primary Sources

Linux:

- `/proc/uptime`
- `/proc/meminfo`
- `/sys/class/power_supply/BAT*`
- `ip addr show`
- `ip route show`
- `/etc/resolv.conf`
- `df -kP`

macOS:

- `sysctl`
- `vm_stat`
- `system_profiler SPPowerDataType`
- `pmset -g batt`
- `diskutil info -all`
- `ifconfig`
- `route -n get default`
- `netstat -rn`
- `scutil --dns`
- `df -kP`

Windows:

- `GetTickCount64`
- `GlobalMemoryStatusEx`
- `GetSystemPowerStatus`
- PowerShell DNS server enumeration with `ipconfig /all` fallback
- `Get-PhysicalDisk`
- `ipconfig /all`
- `route print`
- `arp -a`
- PowerShell CIM queries for optional storage health only

## Live Smoke Validation

- CI now runs a bounded live smoke validation job on GitHub-hosted Ubuntu, macOS, and Windows runners.
- The smoke job runs the existing shared runner with `host`, `resources`, `network`, `routing`, and `dns` selected.
- The smoke job does not enable TCP targets, ping, or traceroute, so it stays focused on local parser and collector drift.
- The smoke summary artifact records platform metadata, execution statuses, counts, and command invocations without persisting raw stdout or stderr.

## Current Limits

- command output still varies by platform and OS version
- Windows cannot execute the macOS `.command` file type directly, so true cross-platform root launch requires a Windows-specific sibling shim even though launch orchestration is shared underneath
- VPN detection remains heuristic
- Linux battery health is limited to what sysfs exposes, and non-privileged Linux storage-device health is still effectively unavailable in the current model
- macOS storage-device health depends on `diskutil` exposing usable device and SMART state on the current host
- Windows battery collection currently captures battery presence, charge, and coarse state without elevation, but it still does not expose design-capacity health in the current model
- Some enterprise Windows environments deny CIM access to standard users; host uptime, memory, resolver inventory, and basic battery state therefore avoid CIM and fall back to native APIs or unprivileged command output
- traceroute parsing remains conservative
- fixture coverage now includes representative split-tunnel, blackhole/default-route, resolver, VPN-adapter, malformed-route, legacy-netstat, and additional traceroute variants across Linux, macOS, and Windows, but it still does not cover every OS/version-localization combination
- live smoke validation now checks real command output on GitHub-hosted Ubuntu, macOS, and Windows images, but it does not yet represent every enterprise image, self-hosted runner baseline, or non-English locale
