#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd -P)"
REPO_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd -P)"
TARGET_DIR="${HOME}/.agents/skills"
SOURCE_DIR="$REPO_ROOT/.agents/skills"

mkdir -p "$TARGET_DIR"

if [ "$(CDPATH= cd -- "$TARGET_DIR" && pwd -P)" = "$SOURCE_DIR" ]; then
  printf 'skills already available at %s\n' "$TARGET_DIR"
  exit 0
fi

for skill in \
  personal-research \
  personal-status \
  personal-memory-search \
  personal-task-intake \
  temporary-file-share \
  karaoke-stem-separation
do
  ln -sfn "$SOURCE_DIR/$skill" "$TARGET_DIR/$skill"
  printf 'linked %s -> %s\n' "$TARGET_DIR/$skill" "$SOURCE_DIR/$skill"
done
