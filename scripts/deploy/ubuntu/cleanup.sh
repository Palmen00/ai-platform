#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${script_dir}/../lib/common.sh"

assert_docker_ready
ensure_deploy_env_file

run_deploy_compose down --remove-orphans
docker image prune -f >/dev/null
docker builder prune -f >/dev/null
