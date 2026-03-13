#!/bin/sh
set -eu

git config core.hooksPath .githooks
echo "Configured git hooks path: .githooks"
