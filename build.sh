#!/usr/bin/env bash
set -euo pipefail

# Rebuild the image after changing Dockerfile/dependencies
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/set_project_env.sh"
cd "${PROJECT_ROOT}"

GIB=$((1024 * 1024 * 1024))
# Current local images are about 7-9 GB, so keep 20 GiB free for a rebuild plus temp layers/cache.
MIN_FREE_SPACE_GB="${MIN_FREE_SPACE_GB:-20}"
MIN_FREE_SPACE_BYTES=$((MIN_FREE_SPACE_GB * GIB))

cleanup_old_docker_artifacts() {
  local age_filter="until=120h"

  echo "Pruning stopped containers older than 5 days..."
  docker container prune --force --filter "${age_filter}"

  echo "Pruning unused images older than 5 days..."
  docker image prune --all --force --filter "${age_filter}"

  echo "Pruning unused networks older than 5 days..."
  docker network prune --force --filter "${age_filter}"

  echo "Pruning build cache older than 5 days..."
  docker buildx prune --force --filter "${age_filter}"
}

ensure_min_free_space() {
  local available_kb available_bytes available_gb mount_point

  available_kb="$(df -Pk "${PROJECT_ROOT}" | awk 'NR==2 {print $4}')"
  available_bytes=$((available_kb * 1024))
  available_gb=$((available_bytes / GIB))
  mount_point="$(df -Pk "${PROJECT_ROOT}" | awk 'NR==2 {print $6}')"

  if [ "${available_bytes}" -lt "${MIN_FREE_SPACE_BYTES}" ]; then
    echo "Only ${available_gb} GiB free on ${mount_point}; need at least ${MIN_FREE_SPACE_GB} GiB before building." >&2
    echo "Set MIN_FREE_SPACE_GB to override the default threshold." >&2
    exit 1
  fi

  echo "Free disk after cleanup: ${available_gb} GiB (minimum required: ${MIN_FREE_SPACE_GB} GiB)."
}

GITHUB_SSH_KEY_PATH="${GITHUB_SSH_KEY_PATH:-${HOME}/.ssh/id_github_codex}"
if [ ! -f "${GITHUB_SSH_KEY_PATH}" ]; then
  echo "GitHub-only SSH key not found: ${GITHUB_SSH_KEY_PATH}" >&2
  echo "Create a dedicated GitHub key or set GITHUB_SSH_KEY_PATH before running build.sh." >&2
  exit 1
fi
export GITHUB_SSH_KEY_PATH

if docker compose version >/dev/null 2>&1; then
  compose_cmd=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  compose_cmd=(docker-compose)
else
  echo "Docker Compose is required but was not found." >&2
  exit 1
fi

cleanup_old_docker_artifacts
ensure_min_free_space

"${compose_cmd[@]}" build

# Start the container in the background
"${compose_cmd[@]}" up -d

# Docker can use lots of memory on computer either by keeping old images or build cache
# to see how much memory run:
# docker system df
# To prune all memory run: docker system prune -af --volumes
