#!/bin/zsh

set -euo pipefail

SCRIPT_PATH=${0:A}
PROJECT_ROOT=${SCRIPT_PATH:h}
BOOTSTRAP_PYTHON="${PROJECT_ROOT}/.venv/bin/python3"
ROOT_LAUNCHER="${PROJECT_ROOT}/src/occams_beard/root_launcher.py"
READY_FILE="${TMPDIR:-/tmp}/occams-beard-ready-${RANDOM}-${RANDOM}.txt"
BACKGROUND_FLAG="--background-launch"
SHOW_TERMINAL_FLAG="--show-terminal"
LOG_FILE="${TMPDIR:-/tmp}/occams-beard-launch-${RANDOM}-${RANDOM}.log"
LAUNCHER_PID=""
BACKGROUND_LAUNCH=0
SHOW_TERMINAL=0
FORWARD_ARGS=()

resolve_bootstrap_python() {
  if [[ -x "${BOOTSTRAP_PYTHON}" ]] && \
    "${BOOTSTRAP_PYTHON}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
      >/dev/null 2>&1; then
    echo "${BOOTSTRAP_PYTHON}"
  else
    echo "python3"
  fi
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

PYTHON_BIN="$(resolve_bootstrap_python)"

cd "${PROJECT_ROOT}"
"${PYTHON_BIN}" "${ROOT_LAUNCHER}" \
  --project-root "${PROJECT_ROOT}" \
  -- \
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
