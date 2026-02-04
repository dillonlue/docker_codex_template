#!/usr/bin/env bash
set -e

source ./set_project_env.sh

docker exec -it "${PROJECT_NAME}" bash
