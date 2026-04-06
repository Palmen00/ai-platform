#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${script_dir}/../lib/common.sh"

assert_docker_ready
ensure_deploy_env_file

if [[ $# -gt 0 ]]; then
  run_deploy_compose logs -f "$1"
else
  run_deploy_compose logs -f
fi
