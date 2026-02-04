#!/usr/bin/env bash
set -euo pipefail

# Upload a Docker tarball to the cluster.
# Usage: ./apptainer/02_local_send.sh [tar_path]
# Example: ./apptainer/02_local_send.sh ./apptainer/project_name.tar
# Assumes you run this from the project root.

if [ ! -f ./set_project_env.sh ] || [ ! -d ./apptainer ]; then
  echo "Error: run from the repo root (directory containing ./set_project_env.sh and ./apptainer)." >&2
  exit 1
fi

source ./set_project_env.sh
source ./apptainer/config.sh

TAR_PATH="${1:-${TAR_PATH:-./apptainer/${PROJECT_NAME}.tar}}"

TAR_BASENAME="$(basename "${TAR_PATH}")"
REMOTE_TAR_PATH="${REMOTE_TAR_PATH:-${REMOTE_REPO_DIR}/apptainer/${TAR_BASENAME}}"

if [ ! -f "${TAR_PATH}" ]; then
  echo "Error: tarball not found: ${TAR_PATH}" >&2
  exit 1
fi

echo "Ensuring remote apptainer directory exists on ${REMOTE_HOST}"
ssh "${REMOTE_HOST}" "mkdir -p \"${REMOTE_REPO_DIR}/apptainer\""

echo "Uploading ${TAR_PATH} to ${REMOTE_HOST}:${REMOTE_TAR_PATH}"
scp "${TAR_PATH}" "${REMOTE_HOST}:${REMOTE_TAR_PATH}"
