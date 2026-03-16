#!/bin/zsh
set -euo pipefail

ROOT="/Users/sebas/personal-agent"
PORT="8082"
HOST="127.0.0.1"
LOG_FILE="/tmp/personal-agent-daemon-8082.log"
PID_FILE="/tmp/personal-agent-daemon-8082.pid"

healthcheck() {
  curl -fsS "http://${HOST}:${PORT}/api/status" >/dev/null 2>&1
}

pid_command_matches() {
  local pid="$1"
  local command
  command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$command" == *"scripts/personal.py daemon"* ]]
}

read_pid_file() {
  if [ -f "$PID_FILE" ]; then
    cat "$PID_FILE"
  fi
}

daemon_pid() {
  local pid
  pid="$(read_pid_file || true)"
  if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null && pid_command_matches "$pid"; then
    echo "$pid"
    return 0
  fi
  return 1
}

find_pid() {
  lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -n 1
}

wait_for_port_state() {
  local want="$1"
  local attempt=0
  while [ "$attempt" -lt 50 ]; do
    local pid
    pid="$(find_pid || true)"
    if [ "$want" = "free" ] && [ -z "${pid:-}" ]; then
      return 0
    fi
    if [ "$want" = "listening" ] && [ -n "${pid:-}" ]; then
      return 0
    fi
    sleep 0.2
    attempt=$((attempt + 1))
  done
  return 1
}

start_daemon() {
  local existing_pid foreign_pid
  existing_pid="$(daemon_pid || true)"
  if [ -n "${existing_pid:-}" ]; then
    if healthcheck; then
      echo "already listening on ${HOST}:${PORT} (pid ${existing_pid})"
      echo "log ${LOG_FILE}"
      exit 0
    fi
    echo "stale daemon pid ${existing_pid}; removing pid file"
    rm -f "$PID_FILE"
  fi
  foreign_pid="$(find_pid || true)"
  if [ -n "${foreign_pid:-}" ]; then
    echo "foreign listener already owns ${HOST}:${PORT} (pid ${foreign_pid}); refusing to start" >&2
    exit 1
  fi

  cd "$ROOT"
  if command -v setsid >/dev/null 2>&1; then
    setsid python3 scripts/personal.py daemon --host "$HOST" --port "$PORT" < /dev/null >"$LOG_FILE" 2>&1 &
  else
    nohup python3 scripts/personal.py daemon --host "$HOST" --port "$PORT" < /dev/null >"$LOG_FILE" 2>&1 &
  fi
  echo $! >"$PID_FILE"

  if ! wait_for_port_state "listening"; then
    echo "failed to start daemon on ${HOST}:${PORT}" >&2
    rm -f "$PID_FILE"
    exit 1
  fi
  if ! healthcheck; then
    echo "daemon opened port but failed healthcheck on ${HOST}:${PORT}" >&2
    rm -f "$PID_FILE"
    exit 1
  fi

  echo "started personal-agent daemon on ${HOST}:${PORT}"
  echo "pid $(daemon_pid || find_pid || true)"
  echo "log ${LOG_FILE}"
}

stop_daemon() {
  local pid
  pid="$(daemon_pid || true)"
  if [ -z "${pid:-}" ]; then
    pid="$(find_pid || true)"
    if [ -n "${pid:-}" ]; then
      echo "foreign listener on ${HOST}:${PORT} (pid ${pid}); refusing to stop it" >&2
      exit 1
    fi
    rm -f "$PID_FILE"
    echo "daemon not running on ${HOST}:${PORT}"
    exit 0
  fi

  kill "$pid"
  if ! wait_for_port_state "free"; then
    echo "daemon did not release ${HOST}:${PORT} after SIGTERM; sending SIGKILL"
    kill -9 "$pid" 2>/dev/null || true
    wait_for_port_state "free"
  fi
  rm -f "$PID_FILE"
  echo "stopped daemon on ${HOST}:${PORT}"
}

status_daemon() {
  local pid
  pid="$(daemon_pid || true)"
  if [ -z "${pid:-}" ]; then
    pid="$(find_pid || true)"
    if [ -n "${pid:-}" ]; then
      echo "foreign listener on ${HOST}:${PORT} (pid ${pid})"
      exit 1
    fi
    echo "daemon not running on ${HOST}:${PORT}"
    exit 1
  fi
  echo "daemon listening on ${HOST}:${PORT}"
  echo "pid ${pid}"
  echo "ui http://${HOST}:${PORT}/"
  echo "status http://${HOST}:${PORT}/api/status"
  if healthcheck; then
    echo "health ok"
  else
    echo "health failing"
    exit 1
  fi
  echo "log ${LOG_FILE}"
}

logs_daemon() {
  touch "$LOG_FILE"
  tail -n 40 "$LOG_FILE"
}

restart_daemon() {
  stop_daemon || true
  start_daemon
}

usage() {
  cat <<EOF
Usage: ./scripts/daemon-8082.sh {start|stop|restart|status|logs}
EOF
}

case "${1:-}" in
  start) start_daemon ;;
  stop) stop_daemon ;;
  restart) restart_daemon ;;
  status) status_daemon ;;
  logs) logs_daemon ;;
  *)
    usage
    exit 1
    ;;
esac
