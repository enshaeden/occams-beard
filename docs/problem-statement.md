# Problem Statement

## What this is

This document defines the operational problem Occam's Beard is meant to address and the scope it keeps intentionally out of bounds.

## Problem space

Endpoint failures often sit between desktop support, systems administration, and network operations. The immediate questions are usually simple but operationally important: whether the host is healthy enough to continue, whether local routing is intact, whether DNS is failing, whether general egress works, whether intended services are reachable, and whether VPN state is relevant. In many environments those answers still come from one-off commands and screenshots, which produces inconsistent evidence and weak handoffs.

## Design approach

Occam's Beard addresses that problem with a bounded local workflow:

- collect a fixed set of host and network facts
- normalize platform-specific output into stable structures
- evaluate deterministic findings against observed evidence
- emit the same result through a terminal report, JSON, and a local web app

The tool is designed to support diagnosis, not remote administration. It avoids background agents, persistent state, and automatic changes to the endpoint.

## Key capabilities

- Host, resource, storage, network, routing, DNS, connectivity, VPN, and service collection
- Deterministic findings tied to explicit evidence
- Separate reasoning for baseline connectivity and intended service reachability
- Local operator workflows through a CLI and a web app using the same runner

## Architecture

The architecture is organized around a narrow execution path: collectors gather evidence, models normalize it, the findings engine evaluates it, and interface layers render it. The shared runner sits between operator input and those layers so the CLI and the web app do not drift.

## Usage

Use this document to understand project scope before reading the implementation details. For execution and output examples, start with [`README.md`](../README.md). For the collection and reasoning model, continue with [`docs/diagnostic-model.md`](diagnostic-model.md) and [`docs/finding-rules.md`](finding-rules.md).

## Tradeoffs and limitations

- The tool does not attempt deep application-layer diagnosis beyond configured service checks.
- It does not infer causes that were not supported by collected evidence.
- It does not manage endpoints, persist historical state, or perform remediation.
- It does not treat missing data as a failure condition unless the observed evidence supports that conclusion.

## Future work

- Refine route interpretation for more policy-routing and split-tunnel cases
- Expand platform fixture coverage where existing command output is still underspecified
