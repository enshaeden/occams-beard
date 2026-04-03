# Problem Statement

Endpoint failures often land in an uncomfortable space between help-desk triage, systems administration, and network troubleshooting. Operators need to answer basic but operationally important questions quickly:

- Is the host healthy enough to troubleshoot further?
- Is the network stack configured correctly?
- Is DNS the problem, or is the problem farther upstream?
- Is a VPN present, and if so, does it appear to be carrying the expected traffic?
- Are disk, memory, or CPU pressure contributing to the reported symptoms?

In many real environments, the first response is still a loose collection of one-off commands, tribal knowledge, and screenshots. That approach does not scale well, is hard to audit, and produces inconsistent handoffs between operators.

Occam's Beard addresses that problem with a narrow, local-first diagnostic workflow:

- collect a bounded set of cross-platform host and network facts
- normalize those facts into a stable model
- evaluate deterministic findings against observed evidence
- emit both human-readable and machine-readable outputs

This makes the tool useful both for direct operator use and as a portfolio artifact demonstrating practical systems engineering judgment.

## Scope

Included:
- host basics
- resource state
- interface and routing state
- DNS tests
- TCP connectivity checks
- optional ping and traceroute
- heuristic VPN indicators
- configurable service and port checks
- deterministic fault-domain analysis

Explicitly excluded:
- remote management
- persistent agents or daemons
- SaaS control planes
- user accounts or RBAC
- cloud storage or synchronization
- automatic remediation actions
- LLM-generated summaries

## Operational Goal

The first release should help a technician or systems engineer answer:

1. Is the endpoint itself unhealthy?
2. Is the fault local to the host or its network segment?
3. Is DNS implicated?
4. Is the issue likely at the internet edge, upstream path, or VPN layer?
5. What evidence supports that conclusion?

That balance of practical scope and disciplined reasoning is the point of the project.
