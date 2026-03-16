#!/bin/zsh
set -euo pipefail

ROOT="/Users/sebas/personal-agent"
HOST="127.0.0.1"
PORT="8082"
LABEL="com.sebas.personal-agent.daemon-8082"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_FILE="/tmp/personal-agent-daemon-8082.log"
ERR_FILE="/tmp/personal-agent-daemon-8082.err.log"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
AGENT_PATH="${AGENT_PATH:-$PATH}"

plist_contents() {
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
    <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>scripts/personal.py</string>
    <string>daemon</string>
    <string>--host</string>
    <string>${HOST}</string>
    <string>--port</string>
    <string>${PORT}</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${ROOT}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_FILE}</string>
  <key>StandardErrorPath</key>
  <string>${ERR_FILE}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
    <key>PATH</key>
    <string>${AGENT_PATH}</string>
  </dict>
</dict>
</plist>
EOF
}

install_agent() {
  mkdir -p "${HOME}/Library/LaunchAgents"
  if [ -z "${PYTHON_BIN:-}" ]; then
    echo "python3 not found" >&2
    exit 1
  fi
  plist_contents > "${PLIST_PATH}"
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "${PLIST_PATH}"
  launchctl kickstart -k "gui/$(id -u)/${LABEL}"
  echo "installed ${LABEL}"
  echo "plist ${PLIST_PATH}"
}

uninstall_agent() {
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
  rm -f "${PLIST_PATH}"
  echo "removed ${LABEL}"
}

status_agent() {
  launchctl print "gui/$(id -u)/${LABEL}"
}

logs_agent() {
  touch "${LOG_FILE}" "${ERR_FILE}"
  echo "stdout ${LOG_FILE}"
  tail -n 40 "${LOG_FILE}"
  echo
  echo "stderr ${ERR_FILE}"
  tail -n 40 "${ERR_FILE}"
}

usage() {
  cat <<EOF
Usage: ./scripts/launchd-8082.sh {install|uninstall|status|logs}
EOF
}

case "${1:-}" in
  install) install_agent ;;
  uninstall) uninstall_agent ;;
  status) status_agent ;;
  logs) logs_agent ;;
  *)
    usage
    exit 1
    ;;
esac
