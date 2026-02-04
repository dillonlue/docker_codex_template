#!/usr/bin/env bash
set -euo pipefail

# Local-only wrapper that uses the argo-70 alias.
# Assumes you run this from the project root.

source ./set_project_env.sh
source ./apptainer/my_config.sh

TAR_PATH="./apptainer/${PROJECT_NAME}.tar"
SIF_PATH="./apptainer/${PROJECT_NAME}.sif"

./apptainer/01_local_build_tar.sh "${PROJECT_NAME}:latest" "${TAR_PATH}"

TAR_BASENAME="$(basename "${TAR_PATH}")"
REMOTE_TAR_PATH="${REMOTE_REPO_DIR}/apptainer/${TAR_BASENAME}"
REMOTE_SIF_PATH="${REMOTE_REPO_DIR}/apptainer/$(basename "${SIF_PATH}")"

ssh "${REMOTE_HOST}" "mkdir -p \"${REMOTE_REPO_DIR}/apptainer\""
scp "${TAR_PATH}" "${REMOTE_HOST}:${REMOTE_TAR_PATH}"

ssh "${REMOTE_HOST}" "cd \"${REMOTE_REPO_DIR}\" && ./apptainer/03_cluster_build.sh \"${REMOTE_TAR_PATH}\" \"${REMOTE_SIF_PATH}\""
