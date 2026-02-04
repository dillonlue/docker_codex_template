#!/usr/bin/env bash
set -euo pipefail

# Run the full local build + send + remote build/run flow.
# Usage: ./apptainer/run_all.sh
# Example: ./apptainer/run_all.sh
# Assumes you run this from the project root.

if [ ! -f ./set_project_env.sh ] || [ ! -d ./apptainer ]; then
  echo "Error: run from the repo root (directory containing ./set_project_env.sh and ./apptainer)." >&2
  exit 1
fi

source ./apptainer/config.sh

./apptainer/01_local_build_tar.sh
./apptainer/02_local_send.sh

ssh "${REMOTE_HOST}" "cd \"${REMOTE_REPO_DIR}\" && ./apptainer/03_cluster_build.sh"
