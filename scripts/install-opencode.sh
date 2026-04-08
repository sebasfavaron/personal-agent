#!/bin/sh
set -eu

REPO_DEFAULT="sebasfavaron/personal-agent"
REF_DEFAULT="main"

REPO="${PERSONAL_AGENT_REPO:-$REPO_DEFAULT}"
REF="${PERSONAL_AGENT_REF:-$REF_DEFAULT}"
RAW_BASE="${PERSONAL_AGENT_RAW_BASE:-https://raw.githubusercontent.com/${REPO}/${REF}}"

SKILLS="personal-research personal-status personal-memory-search personal-approval-queue personal-task-intake"

OPENCODE_DIR="${HOME}/.config/opencode"
AGENTS_DIR="${HOME}/.agents/skills"
RULES_FILE="${OPENCODE_DIR}/AGENTS.md"

say() {
  printf "%s
" "$*"
}

die() {
  printf "error: %s
" "$*" 1>&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

backup_path() {
  path="$1"
  if [ -e "$path" ]; then
    rm -rf "${path}.bck"
    mv "$path" "${path}.bck"
  fi
}

restore_path() {
  path="$1"
  if [ -e "${path}.bck" ]; then
    rm -rf "$path"
    mv "${path}.bck" "$path"
  fi
}

fetch_file() {
  url="$1"
  dest="$2"
  curl -fsSL "$url" -o "$dest"
}

install() {
  require_cmd opencode
  require_cmd curl

  backup_path "$AGENTS_DIR"
  backup_path "$RULES_FILE"

  mkdir -p "$AGENTS_DIR"
  mkdir -p "$OPENCODE_DIR"

  for skill in $SKILLS; do
    skill_dir="$AGENTS_DIR/$skill"
    mkdir -p "$skill_dir"
    fetch_file "$RAW_BASE/.agents/skills/$skill/SKILL.md" "$skill_dir/SKILL.md"
  done

  fetch_file "$RAW_BASE/config/opencode/AGENTS.md" "$RULES_FILE"

  say "installed skills to $AGENTS_DIR"
  say "installed rules to $RULES_FILE"
  say "backup paths: ${AGENTS_DIR}.bck, ${RULES_FILE}.bck"
}

restore() {
  restore_path "$AGENTS_DIR"
  restore_path "$RULES_FILE"
  say "restored backups if present"
}

case "${1:-install}" in
  install)
    install
    ;;
  restore)
    restore
    ;;
  *)
    die "usage: $0 [install|restore]"
    ;;
esac
