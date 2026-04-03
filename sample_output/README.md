# Sample Output

This directory is part of the public review surface for the project.

Each scenario includes machine-readable JSON and a terminal-style report artifact:

- [`healthy-endpoint.json`](healthy-endpoint.json) and [`healthy-endpoint.txt`](healthy-endpoint.txt)
- [`dns-failure.json`](dns-failure.json) and [`dns-failure.txt`](dns-failure.txt)
- [`no-default-route.json`](no-default-route.json) and [`no-default-route.txt`](no-default-route.txt)
- [`high-resource-pressure.json`](high-resource-pressure.json) and [`high-resource-pressure.txt`](high-resource-pressure.txt)
- [`vpn-private-target-failure.json`](vpn-private-target-failure.json) and [`vpn-private-target-failure.txt`](vpn-private-target-failure.txt)

These are illustrative artifacts for static review. They are intentionally realistic, but they are not captured from a live production endpoint.

They also reflect the project's conservative review posture:
- terminal report artifacts and JSON metadata both use the current Occam's Beard naming
- route summaries can show `present`, `missing`, or `suspect` state
- route observations are surfaced when collected route data is incomplete or potentially misleading
- warnings remain the place for degraded collection, not for speculative diagnosis
