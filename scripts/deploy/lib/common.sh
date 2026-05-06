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

  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    if [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]]; then
      continue
    fi
    if [[ "${line}" != *=* ]]; then
      continue
    fi

    local key="${line%%=*}"
    local value="${line#*=}"
    export "${key}=${value}"
  done < "${deploy_env_file}"
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
  ensure_directory "${data_root_host}/app/install"
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

generate_app_secrets_key() {
  python3 - <<'PY'
import base64
import secrets
print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8"))
PY
}

derive_compose_project_name() {
  local seed="${1:-${repo_root}}"
  local digest

  if command -v sha1sum >/dev/null 2>&1; then
    digest="$(printf '%s' "${seed}" | sha1sum | awk '{print substr($1, 1, 8)}')"
  else
    digest="$(printf '%s' "${seed}" | cksum | awk '{print $1}')"
  fi

  printf 'local-ai-os-%s' "${digest}"
}

hash_admin_password() {
  local password="$1"
  ADMIN_PASSWORD_INPUT="${password}" python3 - <<'PY'
import base64
import hashlib
import os
import secrets

password = os.environ["ADMIN_PASSWORD_INPUT"]
salt = secrets.token_bytes(16)
derived = hashlib.scrypt(
    password.encode("utf-8"),
    salt=salt,
    n=2**14,
    r=8,
    p=1,
    dklen=32,
)
encoded_salt = base64.urlsafe_b64encode(salt).decode("utf-8").rstrip("=")
encoded_hash = base64.urlsafe_b64encode(derived).decode("utf-8").rstrip("=")
print(f"scrypt${2**14}$8$1${encoded_salt}${encoded_hash}")
PY
}

run_deploy_compose() {
  load_deploy_env
  # Existing installs created before COMPOSE_PROJECT_NAME used Compose's
  # directory fallback ("infra"). Keep that fallback so updates still target
  # the original stack, while new configured installs get a unique name.
  local compose_project_name="${COMPOSE_PROJECT_NAME:-infra}"

  (
    cd "${repo_root}/infra"
    docker compose --env-file "${deploy_env_file}" -p "${compose_project_name}" -f "${deploy_compose_file}" "$@"
  )
}

timestamp_utc() {
  date -u +"%Y%m%dT%H%M%SZ"
}

write_install_report() {
  load_deploy_env
  ensure_project_directories

  local report_timestamp
  report_timestamp="$(timestamp_utc)"

  local install_dir="${DATA_ROOT_HOST:-${repo_root}/data}/app/install"
  local report_path="${install_dir}/install-report-${report_timestamp}.md"
  local latest_path="${install_dir}/install-report-latest.md"

  local frontend_host="${HOSTNAME_OR_DOMAIN:-127.0.0.1}"
  local backend_host="${HOSTNAME_OR_DOMAIN:-127.0.0.1}"
  local frontend_url="http://${frontend_host}:${FRONTEND_PORT:-3000}"
  local backend_health_url="http://${backend_host}:${BACKEND_PORT:-8000}/health"
  local backend_status_url="http://${backend_host}:${BACKEND_PORT:-8000}/status"
  local qdrant_url="http://127.0.0.1:${QDRANT_PORT:-6333}"

  cat >"${report_path}" <<EOF
# Local AI OS Install Report

- Generated at: ${report_timestamp}
- Env file: ${deploy_env_file}

## Deployment

- Profile: ${INSTALL_PROFILE:-unknown}
- Ollama mode: ${INSTALL_OLLAMA_MODE:-unknown}
- Ollama URL: ${OLLAMA_BASE_URL:-not set}
- Access mode: ${INSTALL_AUTH_MODE:-unknown}
- Bootstrap admin: ${ADMIN_USERNAME:-not set}
- Safe mode: ${SAFE_MODE:-false}
- OCR enabled: ${OCR_ENABLED:-false}
- Connector features: ${INSTALL_CONNECTOR_FEATURES_ENABLED:-${CONNECTOR_FEATURES_ENABLED:-false}}

## Network

- Frontend URL: ${frontend_url}
- Backend health: ${backend_health_url}
- Backend status: ${backend_status_url}
- Qdrant: ${qdrant_url}
- Public API URL: ${NEXT_PUBLIC_API_BASE_URL:-not set}

## Storage

- Data root: ${DATA_ROOT_HOST:-not set}
- Qdrant storage: ${QDRANT_STORAGE_HOST:-not set}

## Support Commands

\`\`\`bash
./scripts/deploy/ubuntu/status.sh
./scripts/deploy/ubuntu/logs.sh backend
./scripts/deploy/ubuntu/stop.sh
./scripts/deploy/ubuntu/update.sh
\`\`\`

## Notes

- Sign in with the bootstrap admin configured during install.
- If auth is disabled, the app starts in local open mode.
- Safe mode blocks higher-risk admin actions when enabled.
EOF

  cp "${report_path}" "${latest_path}"
  printf '%s' "${latest_path}"
}
