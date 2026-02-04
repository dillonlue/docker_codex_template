#!/usr/bin/env bash

# Shared Apptainer configuration. Safe to source; does not change shell options.

APPTAINER_USER="dl4257"
APPTAINER_HOST="argo.princeton.edu"
APPTAINER_REPO_DIR="/Genomics/pritykinlab/dillon/docker_codex_template"

REMOTE_HOST="${REMOTE_HOST:-${APPTAINER_USER}@${APPTAINER_HOST}}"
REMOTE_REPO_DIR="${REMOTE_REPO_DIR:-${APPTAINER_REPO_DIR}}"

export APPTAINER_USER APPTAINER_HOST APPTAINER_REPO_DIR
export REMOTE_HOST REMOTE_REPO_DIR
