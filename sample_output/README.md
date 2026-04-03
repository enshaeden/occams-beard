# Sample Output

This directory contains representative output artifacts for static review.

Each scenario includes machine-readable JSON and a terminal report:

- [`healthy-endpoint.json`](healthy-endpoint.json) and [`healthy-endpoint.txt`](healthy-endpoint.txt)
- [`dns-failure.json`](dns-failure.json) and [`dns-failure.txt`](dns-failure.txt)
- [`no-default-route.json`](no-default-route.json) and [`no-default-route.txt`](no-default-route.txt)
- [`high-resource-pressure.json`](high-resource-pressure.json) and [`high-resource-pressure.txt`](high-resource-pressure.txt)
- [`vpn-private-target-failure.json`](vpn-private-target-failure.json) and [`vpn-private-target-failure.txt`](vpn-private-target-failure.txt)

The artifacts are review fixtures, not live captures from a production endpoint. They show the current Occam's Beard naming, the shared result shape used by the CLI and web app, route states such as `present`, `missing`, or `suspect`, and the separation between warnings, observed facts, and derived findings.
