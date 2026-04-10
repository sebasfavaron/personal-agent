#!/bin/sh
set -eu

REPO_DEFAULT="sebasfavaron/opencode-harness"
REF_DEFAULT="main"

REPO="${PERSONAL_AGENT_REPO:-$REPO_DEFAULT}"
REF="${PERSONAL_AGENT_REF:-$REF_DEFAULT}"
RAW_BASE="${PERSONAL_AGENT_RAW_BASE:-https://raw.githubusercontent.com/${REPO}/${REF}}"

LOCAL_PATH="${PERSONAL_AGENT_LOCAL_PATH:-}"

SKILLS="personal-research personal-status personal-memory-search personal-approval-queue personal-task-intake telegram-notify"

OPENCODE_DIR="${HOME}/.config/opencode"
AGENTS_DIR="${HOME}/.agents/skills"
RULES_FILE="${HOME}/AGENTS.md"
RULES_LINK="${OPENCODE_DIR}/AGENTS.md"

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
  if [ -e "$path" ] || [ -L "$path" ]; then
    rm -rf "${path}.bck"
    mv "$path" "${path}.bck"
  fi
}

restore_path() {
  path="$1"
  if [ -e "${path}.bck" ] || [ -L "${path}.bck" ]; then
    rm -rf "$path"
    mv "${path}.bck" "$path"
  fi
}

fetch_file() {
  url="$1"
  dest="$2"
  curl -fsSL "$url" -o "$dest"
}

ensure_symlink() {
  link="$1"
  target="$2"
  if command -v readlink >/dev/null 2>&1; then
    if [ -L "$link" ]; then
      current="$(readlink "$link" 2>/dev/null || true)"
      if [ "$current" = "$target" ]; then
        return 0
      fi
    fi
  fi
  rm -rf "$link"
  ln -s "$target" "$link"
}

install() {
  require_cmd opencode

  if [ -n "$LOCAL_PATH" ] && [ -d "$LOCAL_PATH" ]; then
    backup_path "$AGENTS_DIR"
    backup_path "$RULES_FILE"
    backup_path "$RULES_LINK"

    mkdir -p "$OPENCODE_DIR"
    mkdir -p "$(dirname "$AGENTS_DIR")"

    rm -rf "$AGENTS_DIR"
    ln -s "$LOCAL_PATH/.agents/skills" "$AGENTS_DIR"

    rm -rf "$RULES_FILE"
    ln -s "$LOCAL_PATH/config/opencode/AGENTS.md" "$RULES_FILE"
    ensure_symlink "$RULES_LINK" "$RULES_FILE"

    say "symlinked skills to $AGENTS_DIR"
    say "symlinked rules to $RULES_FILE"
    say "symlinked rules to $RULES_LINK"
    say "backup paths: ${AGENTS_DIR}.bck, ${RULES_FILE}.bck, ${RULES_LINK}.bck"
    return 0
  fi

  require_cmd curl

  backup_path "$AGENTS_DIR"
  backup_path "$RULES_FILE"
  backup_path "$RULES_LINK"

  mkdir -p "$AGENTS_DIR"
  mkdir -p "$OPENCODE_DIR"

  for skill in $SKILLS; do
    skill_dir="$AGENTS_DIR/$skill"
    mkdir -p "$skill_dir"
    fetch_file "$RAW_BASE/.agents/skills/$skill/SKILL.md" "$skill_dir/SKILL.md"
  done

  fetch_file "$RAW_BASE/.agents/skills/telegram-notify/telegram-notify" "$AGENTS_DIR/telegram-notify/telegram-notify"

  fetch_file "$RAW_BASE/.agents/skills/telegram-notify/.env.example" "$AGENTS_DIR/telegram-notify/.env.example"
  chmod +x "$AGENTS_DIR/telegram-notify/telegram-notify"

  fetch_file "$RAW_BASE/config/opencode/AGENTS.md" "$RULES_FILE"
  ensure_symlink "$RULES_LINK" "$RULES_FILE"

  say "installed skills to $AGENTS_DIR"
  say "installed rules to $RULES_FILE"
  say "symlinked rules to $RULES_LINK"
  say "backup paths: ${AGENTS_DIR}.bck, ${RULES_FILE}.bck, ${RULES_LINK}.bck"
}

restore() {
  restore_path "$AGENTS_DIR"
  restore_path "$RULES_FILE"
  restore_path "$RULES_LINK"
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
