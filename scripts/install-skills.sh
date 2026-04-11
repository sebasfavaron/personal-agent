#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd -P)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)"
TARGET_DIR="${HOME}/.agents/skills"

mkdir -p "$TARGET_DIR"

for skill in \
  personal-research \
  personal-status \
  personal-memory-search \
  personal-approval-queue \
  personal-task-intake \
  temporary-file-share \
  karaoke-stem-separation
do
  ln -sfn "$REPO_ROOT/.agents/skills/$skill" "$TARGET_DIR/$skill"
  printf 'linked %s -> %s\n' "$TARGET_DIR/$skill" "$REPO_ROOT/.agents/skills/$skill"
done
