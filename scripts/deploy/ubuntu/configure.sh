#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${script_dir}/../lib/common.sh"

prompt_with_default() {
  local prompt="$1"
  local default_value="$2"
  local response=""
  read -r -p "${prompt} [${default_value}]: " response
  if [[ -z "${response}" ]]; then
    response="${default_value}"
  fi
  printf '%s' "${response}"
}

prompt_secret() {
  local prompt="$1"
  local response=""
  read -r -s -p "${prompt}: " response
  echo
  printf '%s' "${response}"
}

read_secret_from_file() {
  local file_path="$1"
  if [[ ! -f "${file_path}" ]]; then
    echo "Secret file not found: ${file_path}" >&2
    exit 1
  fi

  python3 - "${file_path}" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
print(path.read_text(encoding="utf-8").splitlines()[0] if path.read_text(encoding="utf-8").splitlines() else "", end="")
PY
}

escape_compose_env_value() {
  # Docker Compose interpolates dollar signs from --env-file values.
  # Password hashes such as scrypt$... must keep literal dollar signs.
  printf '%s' "$1" | sed 's/\$/$$/g'
}

base64_env_value() {
  printf '%s' "$1" | base64 | tr -d '\n'
}

load_answer_file() {
  local file_path="$1"
  if [[ ! -f "${file_path}" ]]; then
    echo "Answer file not found: ${file_path}" >&2
    exit 1
  fi

  while IFS=$'\t' read -r key value; do
    case "${key}" in
      PROFILE)
        if [[ "${profile_cli_set}" != "true" ]]; then
          profile_input="${value}"
        fi
        ;;
      OLLAMA_MODE)
        if [[ "${ollama_mode_cli_set}" != "true" ]]; then
          ollama_mode="${value}"
        fi
        ;;
      OLLAMA_BASE_URL)
        if [[ "${ollama_base_url_cli_set}" != "true" ]]; then
          external_ollama_base_url="${value}"
        fi
        ;;
      AUTH_MODE)
        if [[ "${auth_mode_cli_set}" != "true" ]]; then
          auth_mode="${value}"
        fi
        ;;
      SECURITY_PROFILE)
        if [[ "${security_profile_cli_set}" != "true" ]]; then
          security_profile="${value}"
        fi
        ;;
      ADMIN_USERNAME)
        if [[ "${admin_username_cli_set}" != "true" ]]; then
          admin_username_override="${value}"
        fi
        ;;
      ADMIN_PASSWORD)
        if [[ "${admin_password_cli_set}" != "true" ]]; then
          admin_password_override="${value}"
        fi
        ;;
      ADMIN_PASSWORD_FILE)
        if [[ "${admin_password_file_cli_set}" != "true" ]]; then
          admin_password_file_override="${value}"
        fi
        ;;
      DATA_ROOT)
        if [[ "${data_root_cli_set}" != "true" ]]; then
          data_root_override="${value}"
        fi
        ;;
      FRONTEND_PORT)
        if [[ "${frontend_port_cli_set}" != "true" ]]; then
          frontend_port_override="${value}"
        fi
        ;;
      BACKEND_PORT)
        if [[ "${backend_port_cli_set}" != "true" ]]; then
          backend_port_override="${value}"
        fi
        ;;
      QDRANT_PORT)
        if [[ "${qdrant_port_cli_set}" != "true" ]]; then
          qdrant_port_override="${value}"
        fi
        ;;
      HOSTNAME|HOSTNAME_OR_DOMAIN)
        if [[ "${hostname_cli_set}" != "true" ]]; then
          hostname_or_domain_override="${value}"
        fi
        ;;
      PUBLIC_URL_SCHEME)
        if [[ "${public_url_scheme_cli_set}" != "true" ]]; then
          public_url_scheme_override="${value}"
        fi
        ;;
      OCR_ENABLED)
        if [[ "${ocr_cli_set}" != "true" ]]; then
          ocr_input="${value}"
        fi
        ;;
      CONNECTOR_FEATURES_ENABLED)
        if [[ "${connectors_cli_set}" != "true" ]]; then
          connectors_input="${value}"
        fi
        ;;
      "")
        ;;
      *)
        echo "Unsupported answer file key: ${key}" >&2
        exit 1
        ;;
    esac
  done < <(
    python3 - "${file_path}" <<'PY'
import ast
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if "=" not in line:
        raise SystemExit(f"Invalid answer file line {line_number}: {raw_line}")
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        raise SystemExit(f"Invalid answer file key on line {line_number}")
    if value[:1] in {"'", '"'}:
        try:
            value = ast.literal_eval(value)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"Invalid quoted value for {key} on line {line_number}: {exc}") from exc
    print(f"{key}\t{value}")
PY
  )
}

normalize_yes_no() {
  local value="${1,,}"
  if [[ "${value}" == "y" || "${value}" == "yes" || "${value}" == "true" || "${value}" == "1" ]]; then
    printf 'true'
    return
  fi
  printf 'false'
}

normalize_profile_key() {
  local value="${1,,}"
  case "${value}" in
    light)
      printf 'light'
      ;;
    balanced|balance)
      printf 'balanced'
      ;;
    high|high-performance|high_performance|performance)
      printf 'high'
      ;;
    *)
      printf 'balanced'
      ;;
  esac
}

normalize_ollama_mode() {
  local value="${1,,}"
  case "${value}" in
    local)
      printf 'local'
      ;;
    external)
      printf 'external'
      ;;
    *)
      printf 'local'
      ;;
  esac
}

normalize_security_profile() {
  local value="${1,,}"
  case "${value}" in
    safe)
      printf 'safe'
      ;;
    *)
      printf 'standard'
      ;;
  esac
}

normalize_auth_mode() {
  local value="${1,,}"
  case "${value}" in
    open|local|local-open|local_open|disabled)
      printf 'open'
      ;;
    required|auth|required-login|required_login|login)
      printf 'required'
      ;;
    *)
      printf 'required'
      ;;
  esac
}

normalize_public_url_scheme() {
  local value="${1,,}"
  case "${value}" in
    http)
      printf 'http'
      ;;
    https)
      printf 'https'
      ;;
    *)
      printf 'https'
      ;;
  esac
}

configure_profile_defaults() {
  case "$1" in
    light)
      PROFILE_NAME="Light"
      LOW_IMPACT_MODE="true"
      GLINER_ENABLED="false"
      OLLAMA_EMBED_BATCH_SIZE="2"
      RETRIEVAL_LIMIT="3"
      DOCUMENT_CHUNK_SIZE="900"
      DOCUMENT_CHUNK_OVERLAP="120"
      ;;
    high|high-performance|high_performance)
      PROFILE_NAME="High Performance"
      LOW_IMPACT_MODE="false"
      GLINER_ENABLED="true"
      OLLAMA_EMBED_BATCH_SIZE="16"
      RETRIEVAL_LIMIT="6"
      DOCUMENT_CHUNK_SIZE="1200"
      DOCUMENT_CHUNK_OVERLAP="180"
      ;;
    *)
      PROFILE_NAME="Balanced"
      LOW_IMPACT_MODE="false"
      GLINER_ENABLED="true"
      OLLAMA_EMBED_BATCH_SIZE="8"
      RETRIEVAL_LIMIT="4"
      DOCUMENT_CHUNK_SIZE="1000"
      DOCUMENT_CHUNK_OVERLAP="150"
      ;;
  esac
}

ensure_password() {
  local first=""
  local second=""
  while true; do
    first="$(prompt_secret 'Enter admin password')"
    second="$(prompt_secret 'Confirm admin password')"
    if [[ -z "${first}" ]]; then
      echo "Admin password cannot be empty." >&2
      continue
    fi
    if [[ "${first}" != "${second}" ]]; then
      echo "Passwords did not match. Try again." >&2
      continue
    fi
    printf '%s' "${first}"
    return
  done
}

ensure_username() {
  local username=""
  while true; do
    username="$(prompt_with_default 'Bootstrap admin username' 'Admin')"
    username="${username#"${username%%[![:space:]]*}"}"
    username="${username%"${username##*[![:space:]]}"}"
    if [[ -z "${username}" ]]; then
      echo "Admin username cannot be empty." >&2
      continue
    fi
    printf '%s' "${username}"
    return
  done
}

show_help() {
  cat <<'EOF'
Local AI OS Configure Phase

Usage:
  ./scripts/deploy/ubuntu/configure.sh [options]

Options:
  --non-interactive                 Run without prompts.
  --validate-only                   Validate answers and print summary only.
  --profile <light|balanced|high>   Deployment profile. Default: balanced
  --ollama-mode <local|external>    Ollama mode. Default: local
  --ollama-base-url <url>           Required when using external Ollama
  --answer-file <path>              Load answers from a simple KEY=VALUE file
  --auth-mode <required|open>       Require sign-in or start in open local mode.
                                    Default: required
  --security-profile <standard|safe>
                                    Security profile. Default: standard
  --admin-username <username>       Bootstrap admin username. Default: Admin
  --admin-password <password>       Legacy fallback for non-interactive mode
  --admin-password-file <path>      Preferred for non-interactive mode
  --data-root <path>                Host data root. Default: /opt/local-ai-os/data
  --frontend-port <port>            Default: 3000
  --backend-port <port>             Default: 8000
  --qdrant-port <port>              Default: 6333
  --hostname <hostname>             Optional hostname/domain
  --public-url-scheme <http|https>  Public URL scheme when hostname is set.
                                    Default: https
  --ocr-enabled <yes|no>            Default: yes
  --connector-features-enabled <yes|no>
                                    Default: yes
  -h, --help                        Show this help
EOF
}

non_interactive=false
validate_only=false
profile_input="balanced"
ollama_mode="local"
external_ollama_base_url=""
answer_file_override=""
auth_mode="required"
security_profile="standard"
admin_username_override="Admin"
admin_password_override=""
admin_password_file_override=""
data_root_override="/opt/local-ai-os/data"
frontend_port_override="3000"
backend_port_override="8000"
qdrant_port_override="6333"
hostname_or_domain_override=""
public_url_scheme_override=""
ocr_input="yes"
connectors_input="yes"

profile_cli_set=false
ollama_mode_cli_set=false
ollama_base_url_cli_set=false
auth_mode_cli_set=false
security_profile_cli_set=false
admin_username_cli_set=false
admin_password_cli_set=false
admin_password_file_cli_set=false
data_root_cli_set=false
frontend_port_cli_set=false
backend_port_cli_set=false
qdrant_port_cli_set=false
hostname_cli_set=false
public_url_scheme_cli_set=false
ocr_cli_set=false
connectors_cli_set=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive)
      non_interactive=true
      shift
      ;;
    --validate-only)
      validate_only=true
      shift
      ;;
    --profile)
      profile_input="${2:-}"
      profile_cli_set=true
      shift 2
      ;;
    --ollama-mode)
      ollama_mode="${2:-}"
      ollama_mode_cli_set=true
      shift 2
      ;;
    --ollama-base-url)
      external_ollama_base_url="${2:-}"
      ollama_base_url_cli_set=true
      shift 2
      ;;
    --answer-file)
      answer_file_override="${2:-}"
      shift 2
      ;;
    --auth-mode)
      auth_mode="${2:-}"
      auth_mode_cli_set=true
      shift 2
      ;;
    --security-profile)
      security_profile="${2:-}"
      security_profile_cli_set=true
      shift 2
      ;;
    --admin-username)
      admin_username_override="${2:-}"
      admin_username_cli_set=true
      shift 2
      ;;
    --admin-password)
      admin_password_override="${2:-}"
      admin_password_cli_set=true
      shift 2
      ;;
    --admin-password-file)
      admin_password_file_override="${2:-}"
      admin_password_file_cli_set=true
      shift 2
      ;;
    --data-root)
      data_root_override="${2:-}"
      data_root_cli_set=true
      shift 2
      ;;
    --frontend-port)
      frontend_port_override="${2:-}"
      frontend_port_cli_set=true
      shift 2
      ;;
    --backend-port)
      backend_port_override="${2:-}"
      backend_port_cli_set=true
      shift 2
      ;;
    --qdrant-port)
      qdrant_port_override="${2:-}"
      qdrant_port_cli_set=true
      shift 2
      ;;
    --hostname)
      hostname_or_domain_override="${2:-}"
      hostname_cli_set=true
      shift 2
      ;;
    --public-url-scheme)
      public_url_scheme_override="${2:-}"
      public_url_scheme_cli_set=true
      shift 2
      ;;
    --ocr-enabled)
      ocr_input="${2:-}"
      ocr_cli_set=true
      shift 2
      ;;
    --connector-features-enabled)
      connectors_input="${2:-}"
      connectors_cli_set=true
      shift 2
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      show_help >&2
      exit 1
      ;;
  esac
done

if [[ -n "${answer_file_override}" ]]; then
  load_answer_file "${answer_file_override}"
fi

if [[ "${non_interactive}" != "true" ]]; then
  profile_input="$(prompt_with_default 'Deployment profile (light, balanced, high)' "${profile_input}")"
fi
profile_input="$(normalize_profile_key "${profile_input}")"
configure_profile_defaults "${profile_input}"

if [[ "${non_interactive}" != "true" ]]; then
  ollama_mode="$(prompt_with_default 'Ollama mode (local, external)' "${ollama_mode}")"
fi
ollama_mode="$(normalize_ollama_mode "${ollama_mode}")"
if [[ "${ollama_mode}" == "external" ]]; then
  INSTALL_LOCAL_OLLAMA="false"
  if [[ "${non_interactive}" != "true" ]]; then
    external_ollama_base_url="$(prompt_with_default 'External Ollama API URL' "${external_ollama_base_url:-http://127.0.0.1:11434}")"
  fi
  if [[ -z "${external_ollama_base_url}" ]]; then
    echo "External Ollama mode requires --ollama-base-url." >&2
    exit 1
  fi
  OLLAMA_BASE_URL="${external_ollama_base_url}"
else
  INSTALL_LOCAL_OLLAMA="true"
  OLLAMA_BASE_URL="http://host.docker.internal:11434"
fi

if [[ "${non_interactive}" != "true" ]]; then
  auth_mode="$(prompt_with_default 'Access mode (required, open)' "${auth_mode}")"
fi
auth_mode="$(normalize_auth_mode "${auth_mode}")"
if [[ "${auth_mode}" == "required" ]]; then
  AUTH_ENABLED="true"
else
  AUTH_ENABLED="false"
fi

if [[ "${non_interactive}" != "true" ]]; then
  security_profile="$(prompt_with_default 'Security profile (standard, safe)' "${security_profile}")"
fi
security_profile="$(normalize_security_profile "${security_profile}")"
if [[ "${security_profile}" == "safe" ]]; then
  SAFE_MODE="true"
else
  SAFE_MODE="false"
fi

if [[ "${AUTH_ENABLED}" == "true" ]]; then
  if [[ "${non_interactive}" == "true" ]]; then
    ADMIN_USERNAME="${admin_username_override:-${ADMIN_USERNAME:-Admin}}"
  else
    ADMIN_USERNAME="$(ensure_username)"
  fi

  if [[ "${non_interactive}" == "true" ]]; then
    local_admin_password_file="${admin_password_file_override:-${ADMIN_PASSWORD_FILE:-}}"
    if [[ -n "${local_admin_password_file}" ]]; then
      ADMIN_PASSWORD="$(read_secret_from_file "${local_admin_password_file}")"
    else
      ADMIN_PASSWORD="${admin_password_override:-${ADMIN_PASSWORD:-}}"
    fi
    if [[ -z "${ADMIN_PASSWORD}" ]]; then
      echo "Required auth mode needs --admin-password-file, ADMIN_PASSWORD_FILE, --admin-password, or ADMIN_PASSWORD." >&2
      exit 1
    fi
  else
    ADMIN_PASSWORD="$(ensure_password)"
  fi

  ADMIN_PASSWORD_HASH="$(hash_admin_password "${ADMIN_PASSWORD}")"
  unset ADMIN_PASSWORD
  ADMIN_SESSION_SECRET="$(generate_hex_secret)"
else
  ADMIN_USERNAME="${admin_username_override:-${ADMIN_USERNAME:-Admin}}"
  ADMIN_PASSWORD_HASH=""
  ADMIN_SESSION_SECRET=""
fi
APP_SECRETS_KEY="$(generate_app_secrets_key)"

if [[ "${non_interactive}" != "true" ]]; then
  DATA_ROOT_HOST="$(prompt_with_default 'Host data root' "${data_root_override}")"
else
  DATA_ROOT_HOST="${data_root_override}"
fi
QDRANT_STORAGE_HOST="${DATA_ROOT_HOST}/qdrant"

if [[ "${non_interactive}" != "true" ]]; then
  FRONTEND_PORT="$(prompt_with_default 'Frontend port' "${frontend_port_override}")"
  BACKEND_PORT="$(prompt_with_default 'Backend port' "${backend_port_override}")"
  QDRANT_PORT="$(prompt_with_default 'Qdrant port' "${qdrant_port_override}")"
  HOSTNAME_OR_DOMAIN="$(prompt_with_default 'Hostname or domain (optional)' "${hostname_or_domain_override}")"
else
  FRONTEND_PORT="${frontend_port_override}"
  BACKEND_PORT="${backend_port_override}"
  QDRANT_PORT="${qdrant_port_override}"
  HOSTNAME_OR_DOMAIN="${hostname_or_domain_override}"
fi

if [[ -n "${HOSTNAME_OR_DOMAIN}" ]]; then
  if [[ "${non_interactive}" != "true" ]]; then
    PUBLIC_URL_SCHEME="$(prompt_with_default 'Public URL scheme (https, http)' "${public_url_scheme_override:-https}")"
  else
    PUBLIC_URL_SCHEME="${public_url_scheme_override:-https}"
  fi
  PUBLIC_URL_SCHEME="$(normalize_public_url_scheme "${PUBLIC_URL_SCHEME}")"
  NEXT_PUBLIC_API_BASE_URL="${PUBLIC_URL_SCHEME}://${HOSTNAME_OR_DOMAIN}:${BACKEND_PORT}"
  BACKEND_CORS_ORIGINS="${PUBLIC_URL_SCHEME}://${HOSTNAME_OR_DOMAIN}:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"
else
  PUBLIC_URL_SCHEME="http"
  NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:${BACKEND_PORT}"
  BACKEND_CORS_ORIGINS="http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"
fi
if [[ "${PUBLIC_URL_SCHEME}" == "https" ]]; then
  ADMIN_SESSION_COOKIE_SECURE="true"
else
  ADMIN_SESSION_COOKIE_SECURE="false"
fi

if [[ "${non_interactive}" != "true" ]]; then
  ocr_input="$(prompt_with_default 'Enable OCR stack? (yes, no)' "${ocr_input}")"
fi
OCR_ENABLED="$(normalize_yes_no "${ocr_input}")"
OCRMYPDF_ENABLED="${OCR_ENABLED}"

if [[ "${non_interactive}" != "true" ]]; then
  connectors_input="$(prompt_with_default 'Enable connector features later? (yes, no)' "${connectors_input}")"
fi
CONNECTOR_FEATURES_ENABLED="$(normalize_yes_no "${connectors_input}")"

if [[ "${validate_only}" == "true" ]]; then
  cat <<EOF
Configure validation completed.

Profile: ${PROFILE_NAME}
Ollama mode: ${ollama_mode}
Access mode: ${auth_mode}
Bootstrap admin: ${ADMIN_USERNAME}
Safe mode: ${SAFE_MODE}
OCR enabled: ${OCR_ENABLED}
Connector features: ${CONNECTOR_FEATURES_ENABLED}
Data root: ${DATA_ROOT_HOST}
Frontend port: ${FRONTEND_PORT}
Backend port: ${BACKEND_PORT}
Qdrant port: ${QDRANT_PORT}
Public API URL: ${NEXT_PUBLIC_API_BASE_URL}
Public URL scheme: ${PUBLIC_URL_SCHEME}
Secure auth cookie: ${ADMIN_SESSION_COOKIE_SECURE}
Answer file: ${answer_file_override:-none}

Validation only: no env file written.
EOF
  exit 0
fi

ensure_deploy_env_file

if [[ -f "${deploy_env_file}" ]]; then
  cp "${deploy_env_file}" "${deploy_env_file}.bak"
fi

ADMIN_PASSWORD_HASH_ENV="$(escape_compose_env_value "${ADMIN_PASSWORD_HASH}")"
ADMIN_PASSWORD_HASH_B64="$(base64_env_value "${ADMIN_PASSWORD_HASH}")"
ADMIN_SESSION_SECRET_ENV="$(escape_compose_env_value "${ADMIN_SESSION_SECRET}")"
APP_SECRETS_KEY_ENV="$(escape_compose_env_value "${APP_SECRETS_KEY}")"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(derive_compose_project_name "${repo_root}")}"

umask 077
cat >"${deploy_env_file}" <<EOF
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}
APP_ENV=prod
APP_NAME=Local AI OS
APP_TIMEZONE=Europe/Stockholm
ASSISTANT_INTELLIGENCE_ENABLED=true
ASSISTANT_BASE_PACKS=base,local-ai-os
ASSISTANT_OPTIONAL_PACKS=code,reference
INSTALL_PROFILE=${profile_input}
INSTALL_OLLAMA_MODE=${ollama_mode}
INSTALL_AUTH_MODE=${auth_mode}
INSTALL_SECURITY_PROFILE=${security_profile}
INSTALL_CONNECTOR_FEATURES_ENABLED=${CONNECTOR_FEATURES_ENABLED}
INSTALL_PUBLIC_URL_SCHEME=${PUBLIC_URL_SCHEME}

INSTALL_LOCAL_OLLAMA=${INSTALL_LOCAL_OLLAMA}
OLLAMA_BASE_URL=${OLLAMA_BASE_URL}
OLLAMA_DEFAULT_MODEL=llama3.2:3b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_EMBED_BATCH_SIZE=${OLLAMA_EMBED_BATCH_SIZE}

QDRANT_COLLECTION_NAME=document_chunks
RETRIEVAL_LIMIT=${RETRIEVAL_LIMIT}
RETRIEVAL_MIN_SCORE=0.45
DOCUMENT_CHUNK_SIZE=${DOCUMENT_CHUNK_SIZE}
DOCUMENT_CHUNK_OVERLAP=${DOCUMENT_CHUNK_OVERLAP}

BACKEND_CORS_ORIGINS=${BACKEND_CORS_ORIGINS}
NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

FRONTEND_PORT=${FRONTEND_PORT}
BACKEND_PORT=${BACKEND_PORT}
QDRANT_PORT=${QDRANT_PORT}

DATA_ROOT_HOST=${DATA_ROOT_HOST}
QDRANT_STORAGE_HOST=${QDRANT_STORAGE_HOST}

AUTH_ENABLED=${AUTH_ENABLED}
ADMIN_USERNAME=${ADMIN_USERNAME}
ADMIN_PASSWORD_HASH=${ADMIN_PASSWORD_HASH_ENV}
ADMIN_PASSWORD_HASH_B64=${ADMIN_PASSWORD_HASH_B64}
ADMIN_SESSION_SECRET=${ADMIN_SESSION_SECRET_ENV}
ADMIN_SESSION_TTL_HOURS=12
ADMIN_LOGIN_MAX_ATTEMPTS=5
ADMIN_LOGIN_LOCKOUT_MINUTES=15
ADMIN_LOGIN_IP_MAX_ATTEMPTS=20
ADMIN_LOGIN_IP_WINDOW_SECONDS=300
ADMIN_LOGIN_GLOBAL_MAX_ATTEMPTS=200
ADMIN_LOGIN_GLOBAL_WINDOW_SECONDS=300
ADMIN_SESSION_COOKIE_NAME=local_ai_admin_session
ADMIN_SESSION_COOKIE_SECURE=${ADMIN_SESSION_COOKIE_SECURE}
ADMIN_SESSION_COOKIE_SAMESITE=lax
APP_SECRETS_KEY=${APP_SECRETS_KEY_ENV}
SAFE_MODE=${SAFE_MODE}

LOW_IMPACT_MODE=${LOW_IMPACT_MODE}
GLINER_ENABLED=${GLINER_ENABLED}
OCR_ENABLED=${OCR_ENABLED}
OCRMYPDF_ENABLED=${OCRMYPDF_ENABLED}
OCRMYPDF_USE_DOCKER=true
OCRMYPDF_DOCKER_IMAGE=local-ai-ocrmypdf:latest
OCRMYPDF_AUTO_BUILD=true
OCR_LANGUAGE=eng+swe

CONNECTOR_FEATURES_ENABLED=${CONNECTOR_FEATURES_ENABLED}
EOF
chmod 600 "${deploy_env_file}"

ensure_project_directories

cat <<EOF
Configure phase completed.

Profile: ${PROFILE_NAME}
Ollama mode: ${ollama_mode}
Access mode: ${auth_mode}
Bootstrap admin: ${ADMIN_USERNAME}
Safe mode: ${SAFE_MODE}
OCR enabled: ${OCR_ENABLED}
Data root: ${DATA_ROOT_HOST}
Public URL scheme: ${PUBLIC_URL_SCHEME}
Secure auth cookie: ${ADMIN_SESSION_COOKIE_SECURE}
Env file: ${deploy_env_file}

Next recommended step:
- ./scripts/deploy/ubuntu/deploy.sh
EOF
