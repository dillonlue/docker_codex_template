#!/usr/bin/env bash
set -euo pipefail

# Rebuild the image after changing Dockerfile/dependencies
source ./set_project_env.sh

GITHUB_SSH_KEY_PATH="${GITHUB_SSH_KEY_PATH:-${HOME}/.ssh/id_github_codex}"
if [ ! -f "${GITHUB_SSH_KEY_PATH}" ]; then
  echo "GitHub-only SSH key not found: ${GITHUB_SSH_KEY_PATH}" >&2
  echo "Create a dedicated GitHub key or set GITHUB_SSH_KEY_PATH before running build.sh." >&2
  exit 1
fi
export GITHUB_SSH_KEY_PATH

docker-compose build

# Start the container in the background
docker-compose up -d

# Docker can use lots of memory on computer either by keeping old images or build cache
# to see how much memory run:
# docker system df
# To prune all memory run: docker system prune -af --volumes
