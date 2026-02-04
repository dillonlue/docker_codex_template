#!/usr/bin/env bash
set -euo pipefail

# Reset Codex prompts by copying the repo prompts into ~/.codex/prompts
# Assumes you run this from the project root.

if [ ! -d ./prompts ]; then
  echo "Error: ./prompts not found. Run from the repo root." >&2
  exit 1
fi

mkdir -p "${HOME}/.codex"
rm -rf "${HOME}/.codex/prompts"
cp -R ./prompts "${HOME}/.codex/prompts"

echo "Reset prompts to ${HOME}/.codex/prompts"
