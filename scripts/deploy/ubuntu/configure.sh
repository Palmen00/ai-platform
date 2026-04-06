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

ensure_deploy_env_file

profile_input="$(prompt_with_default 'Deployment profile (light, balanced, high)' 'balanced')"
configure_profile_defaults "${profile_input}"

ollama_mode="$(prompt_with_default 'Ollama mode (local, external)' 'local')"
if [[ "${ollama_mode,,}" == "external" ]]; then
  INSTALL_LOCAL_OLLAMA="false"
  OLLAMA_BASE_URL="$(prompt_with_default 'External Ollama API URL' 'http://127.0.0.1:11434')"
else
  INSTALL_LOCAL_OLLAMA="true"
  OLLAMA_BASE_URL="http://host.docker.internal:11434"
fi

security_profile="$(prompt_with_default 'Security profile (standard, safe)' 'standard')"
if [[ "${security_profile,,}" == "safe" ]]; then
  SAFE_MODE="true"
else
  SAFE_MODE="false"
fi

ADMIN_PASSWORD="$(ensure_password)"
ADMIN_SESSION_SECRET="$(generate_hex_secret)"

DATA_ROOT_HOST="$(prompt_with_default 'Host data root' '/opt/local-ai-os/data')"
QDRANT_STORAGE_HOST="${DATA_ROOT_HOST}/qdrant"

FRONTEND_PORT="$(prompt_with_default 'Frontend port' '3000')"
BACKEND_PORT="$(prompt_with_default 'Backend port' '8000')"
QDRANT_PORT="$(prompt_with_default 'Qdrant port' '6333')"
HOSTNAME_OR_DOMAIN="$(prompt_with_default 'Hostname or domain (optional)' '')"

if [[ -n "${HOSTNAME_OR_DOMAIN}" ]]; then
  NEXT_PUBLIC_API_BASE_URL="http://${HOSTNAME_OR_DOMAIN}:${BACKEND_PORT}"
  BACKEND_CORS_ORIGINS="http://${HOSTNAME_OR_DOMAIN}:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"
else
  NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:${BACKEND_PORT}"
  BACKEND_CORS_ORIGINS="http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"
fi

ocr_input="$(prompt_with_default 'Enable OCR stack? (yes, no)' 'yes')"
OCR_ENABLED="$(normalize_yes_no "${ocr_input}")"
OCRMYPDF_ENABLED="${OCR_ENABLED}"

connectors_input="$(prompt_with_default 'Enable connector features later? (yes, no)' 'yes')"
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
