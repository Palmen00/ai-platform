#!/usr/bin/env bash

set -euo pipefail

get_repo_root() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "${script_dir}/../../.." >/dev/null 2>&1
  pwd
}

repo_root="$(get_repo_root)"
deploy_env_file="${DEPLOY_ENV_FILE:-${repo_root}/.env.ubuntu}"
deploy_compose_file="${repo_root}/infra/docker-compose.deploy.yml"

load_deploy_env() {
  if [[ ! -f "${deploy_env_file}" ]]; then
    return
  fi

  set -a
  # shellcheck disable=SC1090
  . "${deploy_env_file}"
  set +a
}

ensure_directory() {
  local path="$1"
  mkdir -p "${path}"
}

ensure_project_directories() {
  load_deploy_env

  local data_root_host="${DATA_ROOT_HOST:-${repo_root}/data}"
  local qdrant_storage_host="${QDRANT_STORAGE_HOST:-${data_root_host}/qdrant}"

  ensure_directory "${data_root_host}"
  ensure_directory "${data_root_host}/app"
  ensure_directory "${data_root_host}/app/cache"
  ensure_directory "${data_root_host}/app/conversations"
  ensure_directory "${data_root_host}/app/documents"
  ensure_directory "${data_root_host}/app/documents/chunks"
  ensure_directory "${data_root_host}/app/documents/extracted"
  ensure_directory "${data_root_host}/app/connectors"
  ensure_directory "${data_root_host}/app/logs"
  ensure_directory "${data_root_host}/app/ocr/tessdata"
  ensure_directory "${data_root_host}/uploads"
  ensure_directory "${qdrant_storage_host}"
  ensure_directory "${repo_root}/logs"
  ensure_directory "${repo_root}/temp"
}

ensure_deploy_env_file() {
  if [[ -f "${deploy_env_file}" ]]; then
    return
  fi

  cp "${repo_root}/.env.ubuntu.example" "${deploy_env_file}"
  echo "Created ${deploy_env_file}. Review it before starting the stack."
}

assert_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

assert_docker_ready() {
  assert_command docker
  docker compose version >/dev/null 2>&1
}

run_with_sudo() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
    return
  fi

  if ! command -v sudo >/dev/null 2>&1; then
    echo "This command requires root or sudo: $*" >&2
    exit 1
  fi

  sudo "$@"
}

generate_hex_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
    return
  fi

  python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
}

run_deploy_compose() {
  (
    cd "${repo_root}/infra"
    docker compose --env-file "${deploy_env_file}" -f "${deploy_compose_file}" "$@"
  )
}
