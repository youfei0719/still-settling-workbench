#! /usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_SESSION="douyin-script-api"
FRONTEND_SESSION="douyin-script-frontend"
API_LOG="${TMPDIR:-/tmp}/douyin-script-workbench-api.log"
FRONTEND_LOG="${TMPDIR:-/tmp}/douyin-script-workbench-frontend.log"
API_URL="http://127.0.0.1:8000/api/v1/script-workbench/overview"
FRONTEND_URL="http://127.0.0.1:5173/"
LOCAL_ENV="$ROOT/.env.workbench.local"

usage() {
  cat <<EOF
Usage: $0 start|stop|status|logs

start   Start local API and frontend in detached screen sessions when needed.
stop    Stop workbench screen sessions.
status  Show API/frontend health and screen sessions.
logs    Tail local API and frontend logs.
EOF
}

need_screen() {
  if ! command -v screen >/dev/null 2>&1; then
    echo "screen is required for detached local services but was not found." >&2
    exit 1
  fi
}

session_exists() {
  local sessions
  sessions="$(screen -ls 2>/dev/null || true)"
  grep -E "[.]$1[[:space:]]" <<<"$sessions" >/dev/null 2>&1
}

healthy() {
  curl --noproxy '*' -fsS "$1" >/dev/null 2>&1
}

api_listener_pids() {
  lsof -nP -t -iTCP:8000 -sTCP:LISTEN 2>/dev/null || true
}

stop_unmanaged_api_if_workbench() {
  local pids pid command proc_cwd
  pids="$(api_listener_pids)"
  if [ -z "$pids" ]; then
    return 0
  fi
  for pid in $pids; do
    command="$(ps -o command= -p "$pid" 2>/dev/null || true)"
    proc_cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1)"
    if [[ "$command" == *"scripts/dev-workbench-api.py"* && "$proc_cwd" == "$ROOT" ]]; then
      kill "$pid" 2>/dev/null || true
      echo "Stopped unmanaged API process: $pid"
    fi
  done
}

wait_for() {
  local url="$1"
  local label="$2"
  for _ in $(seq 1 30); do
    if healthy "$url"; then
      echo "$label ready: $url"
      return 0
    fi
    sleep 1
  done
  echo "$label did not become ready: $url" >&2
  return 1
}

start_api() {
  if healthy "$API_URL"; then
    if session_exists "$API_SESSION"; then
      echo "API already healthy in managed session: $API_URL"
    else
      echo "API already healthy outside this script: $API_URL"
    fi
    return 0
  fi
  if session_exists "$API_SESSION"; then
    echo "API screen session already exists: $API_SESSION"
  else
    screen -dmS "$API_SESSION" /bin/zsh -lc "cd '$ROOT' && if [ -f '$LOCAL_ENV' ]; then set -a; source '$LOCAL_ENV'; set +a; fi; WORKBENCH_MODEL_WORKER_PYTHON=\${WORKBENCH_MODEL_WORKER_PYTHON:-.venv-model/bin/python} .venv/bin/python scripts/dev-workbench-api.py > '$API_LOG' 2>&1"
    echo "Started API session: $API_SESSION"
  fi
  wait_for "$API_URL" "API"
}

start_frontend() {
  if healthy "$FRONTEND_URL"; then
    if session_exists "$FRONTEND_SESSION"; then
      echo "Frontend already healthy in managed session: $FRONTEND_URL"
    else
      echo "Frontend already healthy outside this script: $FRONTEND_URL"
    fi
    return 0
  fi
  if session_exists "$FRONTEND_SESSION"; then
    echo "Frontend screen session already exists: $FRONTEND_SESSION"
  else
    screen -dmS "$FRONTEND_SESSION" /bin/zsh -lc "cd '$ROOT' && npm run dev --workspace frontend -- --host 127.0.0.1 > '$FRONTEND_LOG' 2>&1"
    echo "Started frontend session: $FRONTEND_SESSION"
  fi
  wait_for "$FRONTEND_URL" "Frontend"
}

start_all() {
  need_screen
  start_api
  start_frontend
  echo "Workbench ready: $FRONTEND_URL"
}

stop_all() {
  if session_exists "$API_SESSION"; then
    screen -S "$API_SESSION" -X quit || true
    echo "Stopped API session: $API_SESSION"
  else
    echo "API session not running: $API_SESSION"
  fi
  stop_unmanaged_api_if_workbench
  if session_exists "$FRONTEND_SESSION"; then
    screen -S "$FRONTEND_SESSION" -X quit || true
    echo "Stopped frontend session: $FRONTEND_SESSION"
  else
    echo "Frontend session not running: $FRONTEND_SESSION"
    if healthy "$FRONTEND_URL"; then
      echo "Frontend is still healthy but was not started by this script; leaving it untouched."
    fi
  fi
}

status_all() {
  if healthy "$API_URL"; then
    if session_exists "$API_SESSION"; then
      echo "API: healthy managed"
    else
      echo "API: healthy unmanaged"
    fi
  else
    echo "API: not healthy"
  fi
  if healthy "$FRONTEND_URL"; then
    if session_exists "$FRONTEND_SESSION"; then
      echo "Frontend: healthy managed"
    else
      echo "Frontend: healthy unmanaged"
    fi
  else
    echo "Frontend: not healthy"
  fi
  echo
  local sessions
  sessions="$(screen -ls 2>/dev/null || true)"
  grep -E "($API_SESSION|$FRONTEND_SESSION)" <<<"$sessions" || echo "No workbench screen sessions."
}

logs_all() {
  echo "API log: $API_LOG"
  echo "Frontend log: $FRONTEND_LOG"
  echo
  tail -n 80 "$API_LOG" 2>/dev/null || true
  echo
  tail -n 80 "$FRONTEND_LOG" 2>/dev/null || true
}

case "${1:-}" in
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  status)
    status_all
    ;;
  logs)
    logs_all
    ;;
  *)
    usage
    exit 2
    ;;
esac
