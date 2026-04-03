#!/bin/zsh

set -euo pipefail

SCRIPT_DIR=${0:A:h}
PROJECT_ROOT=${SCRIPT_DIR:h}
SYSTEM_PYTHON="python3"
PROJECT_VENV="${PROJECT_ROOT}/.venv"
PROJECT_PYTHON3="${PROJECT_VENV}/bin/python3"
PROJECT_PYTHON="${PROJECT_VENV}/bin/python"
READY_FILE="${TMPDIR:-/tmp}/endpoint-diagnostics-lab-ready-${RANDOM}-${RANDOM}.txt"
LAUNCHER_PID=""

resolve_python_bin() {
  if [[ -x "${PROJECT_PYTHON3}" ]]; then
    echo "${PROJECT_PYTHON3}"
  elif [[ -x "${PROJECT_PYTHON}" ]]; then
    echo "${PROJECT_PYTHON}"
  else
    echo "${SYSTEM_PYTHON}"
  fi
}

bootstrap_local_environment() {
  echo "Preparing local operator environment in ${PROJECT_VENV} ..."
  "${SYSTEM_PYTHON}" -m venv "${PROJECT_VENV}"
  "${PROJECT_PYTHON3}" -m pip install --upgrade pip
  "${PROJECT_PYTHON3}" -m pip install -e "${PROJECT_ROOT}"
}

launcher_import_ready() {
  local python_bin="$1"
  PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
    "${python_bin}" -c "from endpoint_diagnostics_lab.launcher import _load_web_dependencies; _load_web_dependencies()" \
    >/dev/null 2>&1
}

cleanup() {
  rm -f "${READY_FILE}"
  if [[ -n "${LAUNCHER_PID}" ]] && kill -0 "${LAUNCHER_PID}" >/dev/null 2>&1; then
    kill "${LAUNCHER_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

PYTHON_BIN="$(resolve_python_bin)"

if ! launcher_import_ready "${PYTHON_BIN}"; then
  bootstrap_local_environment
  PYTHON_BIN="$(resolve_python_bin)"
fi

export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

cd "${PROJECT_ROOT}"
"${PYTHON_BIN}" -m endpoint_diagnostics_lab.launcher --no-browser --ready-file "${READY_FILE}" "$@" &
LAUNCHER_PID=$!

for _ in {1..200}; do
  if [[ -s "${READY_FILE}" ]]; then
    break
  fi
  if ! kill -0 "${LAUNCHER_PID}" >/dev/null 2>&1; then
    wait "${LAUNCHER_PID}"
    exit $?
  fi
  sleep 0.1
done

if [[ ! -s "${READY_FILE}" ]]; then
  echo "Operator interface did not report a ready URL before timeout."
  wait "${LAUNCHER_PID}"
  exit $?
fi

OPERATOR_URL="$(<"${READY_FILE}")"
echo "Opening ${OPERATOR_URL}"
open "${OPERATOR_URL}"
wait "${LAUNCHER_PID}"
