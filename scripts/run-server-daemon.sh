#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8082}"

export PATH="${HOME}/.opencode/bin:${HOME}/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

if [ -d "${REPO_ROOT}/venv" ]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/venv/bin/activate"
fi

if [ -z "${PERSONAL_AGENT_RUNNER_BIN:-}" ]; then
  PERSONAL_AGENT_RUNNER_BIN="$(command -v opencode || true)"
fi

if [ -z "${PERSONAL_AGENT_RUNNER_BIN}" ]; then
  echo "opencode not found on PATH" >&2
  exit 1
fi

export PERSONAL_AGENT_RUNNER_BIN

exec python3 "${REPO_ROOT}/scripts/personal.py" daemon --host "${HOST}" --port "${PORT}"
