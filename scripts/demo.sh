#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

OUTPUT_PATH="${1:-${PROJECT_ROOT}/sample_output/latest-demo.json}"

PYTHONPATH=src python3 -m occams_beard.main run \
  --json-out "${OUTPUT_PATH}" \
  --enable-ping \
  --target github.com:443 \
  --target 1.1.1.1:53
