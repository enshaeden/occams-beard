# Case Studies

These are representative walkthroughs based on deterministic behavior already
supported by the repository. They are not live customer incidents, and they do
not claim production deployment or measured operational impact. Their purpose is
to show what classes of endpoint failures the system is designed to isolate, how
the evidence model behaves under those conditions, and how the support bundle
improves escalation quality.

Each walkthrough should be read alongside [`docs/finding-rules.md`](finding-rules.md)
for the deterministic finding boundary and [`docs/result-schema.md`](result-schema.md)
for the stable result contract.

## Case Study 1: DNS fails while raw IP reachability still works

Reference artifacts:
[`sample_output/profile-dns-issue/result.json`](../sample_output/profile-dns-issue/result.json)
and
[`sample_output/profile-dns-issue/report.txt`](../sample_output/profile-dns-issue/report.txt)

Flow:

```text
User reports "internet is down"
  -> hostname resolution fails
  -> raw IP TCP checks still succeed
  -> deterministic finding isolates DNS path
  -> support receives a bundle that separates resolver failure from general network loss
```

### Operational context

A user cannot reach normal internet destinations by name and reports that the
network appears unavailable. A technician needs to distinguish between a real
network outage and a narrower resolver-path failure before escalating.

### Why ad hoc troubleshooting often fails here

Manual troubleshooting often mixes hostname-based and raw-IP checks without
recording which succeeded and which failed. That can lead to contradictory notes
such as "internet down" alongside evidence that the host can still reach public
infrastructure by IP. The result is a weak handoff because the support record
does not clearly separate DNS failure from transport failure.

### What evidence Occam's Beard collects

The run records local interface and routing state, configured resolvers, DNS
lookups for selected hostnames, and TCP reachability to raw IP targets. In the
committed fixture, resolver inventory is present, all selected hostname lookups
fail, and both raw IP TCP checks succeed.

### What deterministic finding or findings are triggered

The finding triggered is
`dns-failure-raw-ip-success`, titled "DNS resolution failed but raw IP
connectivity succeeded."

### What probable fault domain is surfaced

The surfaced probable fault domain is `dns`.

### What the support bundle contributes to escalation quality

The support bundle preserves the same conclusion in both human and
machine-readable form. `result.json` records the failed DNS checks and
successful TCP checks, `report.txt` explains the fault-domain basis in plain
language, and the manifest and redaction report make the export easier to
review before handoff. That gives the next support tier a clean, reviewable
artifact instead of screenshots or a loosely paraphrased terminal session.

### What next-step decision becomes clearer because of the tool

The support decision becomes narrower: treat the case as a resolver-path issue
first, not as a total endpoint network outage. That makes it more reasonable to
check resolver assignment, split-horizon behavior, DNS policy, or upstream DNS
reachability before escalating into broader network troubleshooting.

### Explicit limitations

This result does not prove whether the failing resolver is local, upstream, or
policy-controlled. It does not prove why the resolver path failed, and it does
not evaluate application-layer behavior beyond the configured checks.

## Case Study 2: A default route exists, but the local path still looks unusable

Reference artifacts:
[`sample_output/degraded-partial/result.json`](../sample_output/degraded-partial/result.json)
and
[`sample_output/degraded-partial/report.txt`](../sample_output/degraded-partial/report.txt)

Flow:

```text
Host appears to have a default route
  -> route points to a suspect or inactive path
  -> interface and route evidence disagree
  -> deterministic finding isolates local network state
  -> escalation starts with a coherent route/interface record
```

### Operational context

A user reports that the endpoint cannot reach external services even though the
system still appears to have a default route. This is the sort of case that
often appears after interface churn, VPN state changes, docking transitions, or
stale local routing state.

### Why ad hoc troubleshooting often fails here

Ad hoc checks often stop too early once a default route is seen. A technician
may record "route present" without noticing that the route points at an
inactive interface, a link-scoped gateway, or an interface that has no usable
address. That can send escalation toward the wrong team because the route table
looks superficially normal.

### What evidence Occam's Beard collects

The tool collects interface inventory, active interface state, local addresses,
route summary, route observations, and generic connectivity results. In the
committed degraded fixture, the default route points to `tun0`, the route state
is marked `suspect`, the interface is not active, and generic external TCP
checks fail.

### What deterministic finding or findings are triggered

The primary finding is `default-route-present-but-inconsistent`, titled "Default
route exists but looks inconsistent with local interface state." The same
fixture also shows a secondary low-severity DNS partial-resolution finding, but
the route inconsistency remains the top deterministic signal.

### What probable fault domain is surfaced

The surfaced probable fault domain is `local_network`.

### What the support bundle contributes to escalation quality

The bundle captures the route observations, the domain execution records, the
warning about route data quality, and the same fault-domain conclusion in
`result.json` and `report.txt`. That matters during escalation because the next
operator can see that the issue is not "no route" in the abstract. It is a more
specific route and interface mismatch with supporting evidence already
normalized.

### What next-step decision becomes clearer because of the tool

The next decision becomes whether to treat the problem as stale or misapplied
local path state before moving upstream. In practice, that means checking the
expected active interface, tunnel state, or recent adapter changes before
assuming a broader WAN or service outage.

### Explicit limitations

This finding does not prove the exact root cause of the inconsistency. It does
not distinguish conclusively between stale local state, policy routing,
incomplete next-hop reachability, or a tunnel client that changed state just
before collection. The tool shows that the route and interface evidence do not
line up cleanly. It does not claim to fully explain why.

## Case Study 3: A VPN-like path is present, but private resources still fail

Reference artifacts:
[`sample_output/profile-vpn-issue/result.json`](../sample_output/profile-vpn-issue/result.json)
and
[`sample_output/profile-vpn-issue/report.txt`](../sample_output/profile-vpn-issue/report.txt)

Flow:

```text
VPN client appears connected
  -> tunnel-like interface and route are present
  -> public baseline succeeds but private target still times out
  -> heuristic VPN finding isolates tunnel-path suspicion
  -> support receives a bundle that separates tunnel presence from private-resource failure
```

### Operational context

A user can reach a public baseline target, but a private service remains
unreachable while a tunnel-like interface is active and the default route uses
that tunnel. This is a common escalation boundary between endpoint support and
network or remote-access teams because the user experience is often reduced to
"VPN says connected, but the app still does not work."

### Why ad hoc troubleshooting often fails here

Ad hoc checks often over-trust the VPN client's visible connected state. They
may prove only that a tunnel exists, not that the tunnel has the right routes,
policy, or remote path to the private target. Without a structured comparison
between the public baseline, the private target, and the tunnel evidence, the
case can bounce between teams.

### What evidence Occam's Beard collects

The committed fixture records interface inventory, route summary, resolver
configuration, public baseline reachability, configured service checks, and VPN
signals. In this scenario, a tunnel-like interface has a usable address, the
default route uses that interface, the public baseline succeeds, and the
private target `10.0.0.10:443` fails.

### What deterministic finding or findings are triggered

The primary finding is `vpn-signal-private-resource-failure`, titled "VPN or
tunnel appears active while private targets remain unreachable." Because this
finding is heuristic by design, the report labels it accordingly rather than
presenting it as a hard proof of VPN root cause.

### What probable fault domain is surfaced

The surfaced probable fault domain is `vpn`.

### What the support bundle contributes to escalation quality

The bundle makes the escalation materially stronger by preserving both sides of
the comparison: evidence that the tunnel path appears active and evidence that
the private service remains unreachable. Support does not have to reconstruct
that relationship from chat logs or screenshots. The exported artifacts show the
same normalized facts, execution records, and probable fault domain in a form
that can be reviewed by a remote-access or network operator.

### What next-step decision becomes clearer because of the tool

The clearer next decision is to escalate along the VPN or private-route path
rather than treating the case as a general internet outage. That narrows the
follow-up to tunnel routing, access policy, remote network reachability, or the
private service path itself.

### Explicit limitations

This finding does not prove that the VPN stack is healthy end to end. It does
not prove whether the failure is caused by tunnel routing, security policy,
split access rules, or the private target itself. It shows only that the tool
can see credible local tunnel evidence while private-resource checks still fail.

## What these examples prove about the system design

Taken together, these walkthroughs show why the repository is organized around
deterministic evidence, a stable result object, and support-ready export rather
than around a transient UI or a conversational diagnosis surface.

- The same core result can support self-service reading, technician review, and
  escalation handoff without re-running the reasoning in a different layer.
- The findings stay tied to collected evidence, which keeps the system
  inspectable and limits over-claiming.
- Support bundles matter because they preserve the reasoning context around the
  finding, not just the conclusion.
- The case studies also show an intentional operational boundary: the tool is
  designed to isolate fault domains and strengthen escalation, not to replace
  network engineering, application debugging, or remediation workflows.
