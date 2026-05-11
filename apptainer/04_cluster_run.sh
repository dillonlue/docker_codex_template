#!/usr/bin/env bash
set -euo pipefail

# Run a bash shell or command inside an Apptainer SIF.
# Usage: ./apptainer/04_cluster_run.sh [sif_path] [command ...]
# Example: ./apptainer/04_cluster_run.sh ./apptainer/project_name.sif
# Example: ./apptainer/04_cluster_run.sh ./apptainer/project_name.sif pwd
# Assumes you run this from the project root.

if [ ! -f ./set_project_env.sh ] || [ ! -d ./apptainer ]; then
  echo "Error: run from the repo root (directory containing ./set_project_env.sh and ./apptainer)." >&2
  echo "Example (cluster): cd /Genomics/pritykinlab/dillon/docker_codex_template_v2" >&2
  exit 1
fi

source ./set_project_env.sh
HOST_REPO_DIR="$(pwd)"
HOST_APPTAINER_HOME="${HOME}/.apptainer_home"
CONTAINER_HOME="/home/apptainer"
HOST_CODEX_DIR="${HOME}/.codex"
CONTAINER_CODEX_DIR="${CONTAINER_HOME}/.codex"
HOST_SSH_DIR="${HOME}/.ssh"
HOST_GITCONFIG="${HOME}/.gitconfig"
CONTAINER_GITCONFIG="${CONTAINER_HOME}/.gitconfig"
HOST_MY_UTILS_DIR="${HOST_MY_UTILS_DIR:-/Genomics/pritykinlab/dillon/my_utils}"
CONTAINER_MY_UTILS_DIR="${CONTAINER_MY_UTILS_DIR:-/my_utils}"

SIF_PATH="${1:-${SIF_PATH:-./apptainer/${PROJECT_NAME}.sif}}"
if [ "$#" -gt 0 ]; then
  shift
fi
USE_NV="${USE_NV:-auto}"

if [ ! -f "${SIF_PATH}" ]; then
  echo "Error: SIF not found: ${SIF_PATH}" >&2
  echo "Run ./apptainer/03_cluster_build.sh first." >&2
  exit 1
fi

mkdir -p "${HOST_APPTAINER_HOME}"
BIND_ARGS=(
  --bind "${HOST_APPTAINER_HOME}:${CONTAINER_HOME}"
  --bind "${HOST_REPO_DIR}:/repo"
  --bind "${HOST_CODEX_DIR}:${CONTAINER_CODEX_DIR}"
)
NV_ARGS=()
if [ "${USE_NV}" = "1" ] || [ "${USE_NV}" = "true" ]; then
  NV_ARGS=(--nv)
elif [ "${USE_NV}" = "auto" ]; then
  if command -v nvidia-smi >/dev/null 2>&1 || [ -e /dev/nvidia0 ]; then
    NV_ARGS=(--nv)
  fi
fi
if [ -d "${HOST_SSH_DIR}" ]; then
  BIND_ARGS+=(--bind "${HOST_SSH_DIR}:${CONTAINER_HOME}/.ssh")
else
  echo "Warning: ${HOST_SSH_DIR} not found; skipping SSH bind."
fi
if [ -f "${HOST_GITCONFIG}" ]; then
  BIND_ARGS+=(--bind "${HOST_GITCONFIG}:${CONTAINER_GITCONFIG}")
else
  echo "Warning: ${HOST_GITCONFIG} not found; skipping gitconfig bind."
fi
if [ -d "${HOST_MY_UTILS_DIR}" ]; then
  BIND_ARGS+=(--bind "${HOST_MY_UTILS_DIR}:${CONTAINER_MY_UTILS_DIR}")
else
  echo "Warning: ${HOST_MY_UTILS_DIR} not found; skipping my_utils bind."
fi

if [ "$#" -gt 0 ]; then
  echo "Running inside container: $*"
  apptainer exec --cleanenv --no-home --home "${CONTAINER_HOME}" \
    "${NV_ARGS[@]}" \
    "${BIND_ARGS[@]}" \
    "${SIF_PATH}" \
    bash --noprofile --norc -lc 'mkdir -p "$1" && export MY_UTILS_DIR="$2" && MY_UTILS_PARENT="$(dirname "$MY_UTILS_DIR")" && export PYTHONPATH="${MY_UTILS_PARENT}${PYTHONPATH:+:${PYTHONPATH}}" && cd /repo && shift 2 && exec "$@"' \
    bash "${CONTAINER_HOME}" "${CONTAINER_MY_UTILS_DIR}" "$@"
else
  echo "Running: bash"
  apptainer exec --cleanenv --no-home --home "${CONTAINER_HOME}" \
    "${NV_ARGS[@]}" \
    "${BIND_ARGS[@]}" \
    "${SIF_PATH}" \
    bash --noprofile --norc -lc 'mkdir -p "$1" && export MY_UTILS_DIR="$2" && MY_UTILS_PARENT="$(dirname "$MY_UTILS_DIR")" && export PYTHONPATH="${MY_UTILS_PARENT}${PYTHONPATH:+:${PYTHONPATH}}" && cd /repo && exec bash --noprofile --norc' \
    bash "${CONTAINER_HOME}" "${CONTAINER_MY_UTILS_DIR}"
fi
