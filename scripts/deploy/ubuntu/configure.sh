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

show_help() {
  cat <<'EOF'
Local AI OS Configure Phase

Usage:
  ./scripts/deploy/ubuntu/configure.sh [options]

Options:
  --non-interactive                 Run without prompts.
  --profile <light|balanced|high>   Deployment profile. Default: balanced
  --ollama-mode <local|external>    Ollama mode. Default: local
  --ollama-base-url <url>           Required when using external Ollama
  --security-profile <standard|safe>
                                    Security profile. Default: standard
  --admin-password <password>       Required in non-interactive mode
  --data-root <path>                Host data root. Default: /opt/local-ai-os/data
  --frontend-port <port>            Default: 3000
  --backend-port <port>             Default: 8000
  --qdrant-port <port>              Default: 6333
  --hostname <hostname>             Optional hostname/domain
  --ocr-enabled <yes|no>            Default: yes
  --connector-features-enabled <yes|no>
                                    Default: yes
  -h, --help                        Show this help
EOF
}

non_interactive=false
profile_input="balanced"
ollama_mode="local"
external_ollama_base_url=""
security_profile="standard"
admin_password_override=""
data_root_override="/opt/local-ai-os/data"
frontend_port_override="3000"
backend_port_override="8000"
qdrant_port_override="6333"
hostname_or_domain_override=""
ocr_input="yes"
connectors_input="yes"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive)
      non_interactive=true
      shift
      ;;
    --profile)
      profile_input="${2:-}"
      shift 2
      ;;
    --ollama-mode)
      ollama_mode="${2:-}"
      shift 2
      ;;
    --ollama-base-url)
      external_ollama_base_url="${2:-}"
      shift 2
      ;;
    --security-profile)
      security_profile="${2:-}"
      shift 2
      ;;
    --admin-password)
      admin_password_override="${2:-}"
      shift 2
      ;;
    --data-root)
      data_root_override="${2:-}"
      shift 2
      ;;
    --frontend-port)
      frontend_port_override="${2:-}"
      shift 2
      ;;
    --backend-port)
      backend_port_override="${2:-}"
      shift 2
      ;;
    --qdrant-port)
      qdrant_port_override="${2:-}"
      shift 2
      ;;
    --hostname)
      hostname_or_domain_override="${2:-}"
      shift 2
      ;;
    --ocr-enabled)
      ocr_input="${2:-}"
      shift 2
      ;;
    --connector-features-enabled)
      connectors_input="${2:-}"
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

ensure_deploy_env_file

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
  security_profile="$(prompt_with_default 'Security profile (standard, safe)' "${security_profile}")"
fi
security_profile="$(normalize_security_profile "${security_profile}")"
if [[ "${security_profile}" == "safe" ]]; then
  SAFE_MODE="true"
else
  SAFE_MODE="false"
fi

if [[ "${non_interactive}" == "true" ]]; then
  ADMIN_PASSWORD="${admin_password_override:-${ADMIN_PASSWORD:-}}"
  if [[ -z "${ADMIN_PASSWORD}" ]]; then
    echo "Non-interactive mode requires --admin-password or ADMIN_PASSWORD in the environment." >&2
    exit 1
  fi
else
  ADMIN_PASSWORD="$(ensure_password)"
fi
ADMIN_SESSION_SECRET="$(generate_hex_secret)"

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
  NEXT_PUBLIC_API_BASE_URL="http://${HOSTNAME_OR_DOMAIN}:${BACKEND_PORT}"
  BACKEND_CORS_ORIGINS="http://${HOSTNAME_OR_DOMAIN}:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"
else
  NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:${BACKEND_PORT}"
  BACKEND_CORS_ORIGINS="http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"
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

if [[ -f "${deploy_env_file}" ]]; then
  cp "${deploy_env_file}" "${deploy_env_file}.bak"
fi

cat >"${deploy_env_file}" <<EOF
APP_ENV=prod
APP_NAME=Local AI OS

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

AUTH_ENABLED=true
ADMIN_PASSWORD=${ADMIN_PASSWORD}
ADMIN_SESSION_SECRET=${ADMIN_SESSION_SECRET}
ADMIN_SESSION_TTL_HOURS=12
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

ensure_project_directories

cat <<EOF
Configure phase completed.

Profile: ${PROFILE_NAME}
Ollama mode: ${ollama_mode}
Safe mode: ${SAFE_MODE}
OCR enabled: ${OCR_ENABLED}
Data root: ${DATA_ROOT_HOST}
Env file: ${deploy_env_file}

Next recommended step:
- ./scripts/deploy/ubuntu/deploy.sh
EOF
