# Platform Notes

## General Rules

- Baseline collection remains non-privileged.
- Missing commands degrade into warnings or `unsupported` execution status instead of silent skips.
- Optional ping and traceroute remain best-effort.
- Raw command capture is opt-in and local only.
- The bounded process-snapshot commands used for host-pressure hints stay excluded from raw command capture so support bundles do not export raw process inventories.
- Repo-root operator launch now uses platform-specific root shims that delegate to one shared Python bootstrap module; macOS keeps `Open Device Check.command`, and Windows uses `Open Device Check.cmd`.
- The repo-root launcher now rejects an existing project virtualenv interpreter when it is older than the supported Python baseline, so stale local `.venv` state does not block browser launch.

## Primary Sources

Linux:

- `/proc/uptime`
- `/proc/meminfo`
- `/etc/timezone` or `/etc/localtime`
- `/sys/class/power_supply/BAT*`
- `ps -A -o comm=,pcpu=,rss=`
- `ip addr show`
- `ip route show`
- `/etc/resolv.conf`
- `df -kP`

macOS:

- `sysctl`
- `vm_stat`
- `sysctl vm.swapusage`
- `/etc/localtime`
- `system_profiler SPPowerDataType`
- `pmset -g batt`
- `ps -A -o comm=,pcpu=,rss=`
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
- `tzutil /g`
- `Get-Process | Select-Object ProcessName,CPU,WorkingSet64`
- PowerShell DNS server enumeration with `ipconfig /all` fallback
- `Get-PhysicalDisk`
- `ipconfig /all`
- `route print`
- `arp -a`
- PowerShell CIM queries for optional storage health only
- optional one-shot verified HTTPS response `Date` header for bounded clock-skew comparison when the operator enables it

## Live Smoke Validation

- CI now runs a bounded live smoke validation job on GitHub-hosted Ubuntu, macOS, and Windows runners.
- The smoke job runs the existing shared runner with `host`, `resources`, `network`, `routing`, and `dns` selected.
- The smoke job does not enable TCP targets, ping, or traceroute, so it stays focused on local parser and collector drift.
- The smoke summary artifact records platform metadata, execution statuses, counts, and command invocations without persisting raw stdout or stderr.

## Current Limits

- command output still varies by platform and OS version
- Windows cannot execute the macOS `.command` file type directly, so true cross-platform root launch requires a Windows-specific sibling shim even though launch orchestration is shared underneath
- VPN detection remains heuristic
- local time collection is snapshot-only; it captures the current wall clock, UTC offset, and best-effort timezone identifier, not a sustained drift history
- the optional clock-skew probe uses one bounded verified HTTPS response date, reports inconclusive when certificate validation fails, and intentionally avoids any time-sync or remediation behavior
- Linux and macOS timezone identifiers are best-effort and depend on local configuration files or symlink layout exposing an IANA zone name cleanly
- Linux battery health is limited to what sysfs exposes, and non-privileged Linux storage-device health is still effectively unavailable in the current model
- Linux storage pressure now ignores pseudo-filesystems such as `/proc`, `/run`, `/sys`, and `/dev/shm` so operator findings stay focused on real writable volumes
- Linux can expose swap and commit pressure from `/proc/meminfo`, but not every distribution or containerized runtime exposes the same fields consistently
- macOS storage-device health depends on `diskutil` exposing usable device and SMART state on the current host
- macOS and Linux can expose timezone identifiers locally, but not every endpoint preserves them in a stable or parseable form
- macOS and Linux storage-space findings are based on `df` plus non-privileged filesystem usage snapshots; they show current free-space pressure only and do not represent a sustained trend
- macOS can expose swap usage, but it does not expose the same commit-limit semantics as Linux in the current non-privileged model
- Windows battery collection currently captures battery presence, charge, and coarse state without elevation, but it still does not expose design-capacity health in the current model
- Windows timezone identifiers come from `tzutil /g`, which returns Windows timezone names rather than IANA identifiers
- Windows storage-device health remains opportunistic because some environments expose only coarse `Get-PhysicalDisk` health states and some deny the query to standard users
- Windows process hints currently lean more on working-set size than on true instantaneous CPU saturation because the standard unprivileged process snapshot is coarser there
- process hints are snapshot-only and category-based; they are intentionally not a full process list or a sustained trend view
- Storage-device health remains intentionally bounded. The project does not perform destructive disk testing, privileged repair actions, or broad vendor-specific SMART parsing.
- Some enterprise Windows environments deny CIM access to standard users; host uptime, memory, resolver inventory, and basic battery state therefore avoid CIM and fall back to native APIs or unprivileged command output
- traceroute parsing remains conservative
- fixture coverage now includes representative split-tunnel, blackhole/default-route, resolver, VPN-adapter, malformed-route, legacy-netstat, and additional traceroute variants across Linux, macOS, and Windows, but it still does not cover every OS/version-localization combination
- live smoke validation now checks real command output on GitHub-hosted Ubuntu, macOS, and Windows images, but it does not yet represent every enterprise image, self-hosted runner baseline, or non-English locale
