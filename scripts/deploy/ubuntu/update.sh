#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${script_dir}/../lib/common.sh"

assert_docker_ready
ensure_project_directories
ensure_deploy_env_file

run_deploy_compose pull qdrant
run_deploy_compose up -d --build --remove-orphans
