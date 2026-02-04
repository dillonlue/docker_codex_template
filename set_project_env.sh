#!/usr/bin/env bash

# Shared project environment variables.
# This file is safe to source; it does not change shell options.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME_FILE="${PROJECT_NAME_FILE:-${PROJECT_ROOT}/.project_directory_name.txt}"

PROJECT_NAME="${PROJECT_NAME:-}"
if [ -z "${PROJECT_NAME}" ] && [ -f "${PROJECT_NAME_FILE}" ]; then
  PROJECT_NAME="$(tr -d '\r\n' < "${PROJECT_NAME_FILE}")"
fi
if [ -z "${PROJECT_NAME}" ]; then
  PROJECT_NAME="$(basename "${PROJECT_ROOT}")"
fi

export PROJECT_ROOT PROJECT_NAME
