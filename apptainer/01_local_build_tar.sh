#!/usr/bin/env bash
set -euo pipefail

# Build the Docker image locally and save it as a tarball for transfer.
# Usage: ./apptainer/01_local_build_tar.sh [image_name] [tar_path]
# Example: ./apptainer/01_local_build_tar.sh project_name:latest ./apptainer/project_name.tar
# Assumes you run this from the project root.

if [ ! -f ./set_project_env.sh ] || [ ! -d ./apptainer ]; then
  echo "Error: run from the repo root (directory containing ./set_project_env.sh and ./apptainer)." >&2
  exit 1
fi

source ./set_project_env.sh
IMAGE_NAME="${1:-${IMAGE_NAME:-${PROJECT_NAME}:latest}}"
TAR_PATH="${2:-${TAR_PATH:-./apptainer/${PROJECT_NAME}.tar}}"
DOCKERFILE_DIR="."

echo "Building Docker image: ${IMAGE_NAME} (linux/amd64)"
docker buildx build --platform linux/amd64 -t "${IMAGE_NAME}" --load "${DOCKERFILE_DIR}"

echo "Saving Docker image to: ${TAR_PATH}"
docker save -o "${TAR_PATH}" "${IMAGE_NAME}"
