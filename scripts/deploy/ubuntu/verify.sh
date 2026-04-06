#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${script_dir}/../lib/common.sh"

wait_for_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-30}"
  local delay_seconds="${4:-2}"

  for ((attempt=1; attempt<=attempts; attempt+=1)); do
    if curl -fsS "${url}" >/dev/null 2>&1; then
      echo "OK: ${label}"
      return
    fi
    sleep "${delay_seconds}"
  done

  echo "FAILED: ${label} (${url})" >&2
  exit 1
}

assert_docker_ready
ensure_deploy_env_file
load_deploy_env

wait_for_http "http://127.0.0.1:${BACKEND_PORT:-8000}/health" "Backend health"
wait_for_http "http://127.0.0.1:${BACKEND_PORT:-8000}/status" "Backend status"
wait_for_http "http://127.0.0.1:${BACKEND_PORT:-8000}/models" "Backend models"
wait_for_http "http://127.0.0.1:${FRONTEND_PORT:-3000}" "Frontend"
wait_for_http "http://127.0.0.1:${QDRANT_PORT:-6333}/collections" "Qdrant"

if [[ "${INSTALL_LOCAL_OLLAMA:-false}" == "true" ]]; then
  wait_for_http "${OLLAMA_BASE_URL:-http://127.0.0.1:11434}/api/tags" "Local Ollama"
else
  wait_for_http "${OLLAMA_BASE_URL:-http://127.0.0.1:11434}/api/tags" "External Ollama"
fi

run_deploy_compose exec -T backend tesseract --version >/dev/null
echo "OK: Backend container can access Tesseract"

run_deploy_compose exec -T backend docker version >/dev/null
echo "OK: Backend container can access Docker for OCRmyPDF"

install_report_path="$(write_install_report)"

cat <<EOF
Verification completed successfully.

Frontend: http://127.0.0.1:${FRONTEND_PORT:-3000}
Backend health: http://127.0.0.1:${BACKEND_PORT:-8000}/health
Backend status: http://127.0.0.1:${BACKEND_PORT:-8000}/status
Qdrant: http://127.0.0.1:${QDRANT_PORT:-6333}
Install report: ${install_report_path}

Recommended support commands:
- ./scripts/deploy/ubuntu/status.sh
- ./scripts/deploy/ubuntu/logs.sh backend
- ./scripts/deploy/ubuntu/stop.sh
- ./scripts/deploy/ubuntu/update.sh
EOF
