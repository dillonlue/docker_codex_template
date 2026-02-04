#!/usr/bin/env bash
set -euo pipefail

# Build an Apptainer SIF from a Docker tarball.
# Usage: ./apptainer/03_cluster_build.sh [tar_path] [sif_path]
# Example: ./apptainer/03_cluster_build.sh ./apptainer/project_name.tar ./apptainer/project_name.sif
# Assumes you run this from the project root.

if [ ! -f ./set_project_env.sh ] || [ ! -d ./apptainer ]; then
  echo "Error: run from the repo root (directory containing ./set_project_env.sh and ./apptainer)." >&2
  echo "Example (cluster): cd /Genomics/pritykinlab/dillon/docker_codex_template" >&2
  exit 1
fi

source ./set_project_env.sh
TAR_PATH="${1:-${TAR_PATH:-./apptainer/${PROJECT_NAME}.tar}}"
SIF_PATH="${2:-${SIF_PATH:-./apptainer/${PROJECT_NAME}.sif}}"

if [ ! -f "${TAR_PATH}" ]; then
  echo "Error: tarball not found: ${TAR_PATH}" >&2
  exit 1
fi

echo "Removing existing SIF (if any): ${SIF_PATH}"
rm -f "${SIF_PATH}"

echo "Building SIF: ${SIF_PATH}"
apptainer build "${SIF_PATH}" "docker-archive://${TAR_PATH}"
