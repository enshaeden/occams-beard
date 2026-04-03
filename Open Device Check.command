#!/bin/zsh

set -euo pipefail

SCRIPT_PATH=${0:A}
PROJECT_ROOT=${SCRIPT_PATH:h}
SYSTEM_PYTHON="python3"
PROJECT_VENV="${PROJECT_ROOT}/.venv"
PROJECT_PYTHON3="${PROJECT_VENV}/bin/python3"
PROJECT_PYTHON="${PROJECT_VENV}/bin/python"
READY_FILE="${TMPDIR:-/tmp}/occams-beard-ready-${RANDOM}-${RANDOM}.txt"
BACKGROUND_FLAG="--background-launch"
SHOW_TERMINAL_FLAG="--show-terminal"
LOG_FILE="${TMPDIR:-/tmp}/occams-beard-launch-${RANDOM}-${RANDOM}.log"
LAUNCHER_PID=""
BACKGROUND_LAUNCH=0
SHOW_TERMINAL=0
FORWARD_ARGS=()

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
    "${python_bin}" -c "from occams_beard.launcher import _load_web_dependencies; _load_web_dependencies()" \
    >/dev/null 2>&1
}

hide_terminal_window() {
  if [[ "${TERM_PROGRAM:-}" != "Apple_Terminal" ]]; then
    return
  fi

  /usr/bin/osascript >/dev/null 2>&1 <<'APPLESCRIPT' || true
tell application "Terminal"
  try
    set miniaturized of front window to true
  end try
  try
    set visible to false
  end try
end tell
APPLESCRIPT
}

cleanup() {
  rm -f "${READY_FILE}"
  if [[ -n "${LAUNCHER_PID}" ]] && kill -0 "${LAUNCHER_PID}" >/dev/null 2>&1; then
    kill "${LAUNCHER_PID}" >/dev/null 2>&1 || true
  fi
}

for arg in "$@"; do
  case "${arg}" in
    "${BACKGROUND_FLAG}")
      BACKGROUND_LAUNCH=1
      ;;
    "${SHOW_TERMINAL_FLAG}")
      SHOW_TERMINAL=1
      ;;
    *)
      FORWARD_ARGS+=("${arg}")
      ;;
  esac
done

if (( ! BACKGROUND_LAUNCH && ! SHOW_TERMINAL )) && [[ "${TERM_PROGRAM:-}" == "Apple_Terminal" ]]; then
  nohup "${SCRIPT_PATH}" "${BACKGROUND_FLAG}" "${FORWARD_ARGS[@]}" >"${LOG_FILE}" 2>&1 < /dev/null &
  hide_terminal_window
  exit 0
fi

trap cleanup EXIT INT TERM

PYTHON_BIN="$(resolve_python_bin)"

if ! launcher_import_ready "${PYTHON_BIN}"; then
  bootstrap_local_environment
  PYTHON_BIN="$(resolve_python_bin)"
fi

export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

cd "${PROJECT_ROOT}"
"${PYTHON_BIN}" -m occams_beard.launcher \
  --no-browser \
  --shutdown-on-browser-close \
  --ready-file "${READY_FILE}" \
  "${FORWARD_ARGS[@]}" &
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
