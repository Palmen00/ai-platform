#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${script_dir}/../lib/common.sh"

install_local_ollama_if_needed() {
  load_deploy_env
  if [[ "${INSTALL_LOCAL_OLLAMA:-false}" != "true" ]]; then
    return
  fi

  if command -v ollama >/dev/null 2>&1; then
    if run_with_sudo systemctl enable --now ollama >/dev/null 2>&1; then
      return
    fi
  fi

  if [[ "${EUID}" -eq 0 ]]; then
    curl -fsSL https://ollama.com/install.sh | sh
  else
    curl -fsSL https://ollama.com/install.sh | sudo sh
  fi
  run_with_sudo systemctl enable --now ollama
}

configure_local_ollama_service_binding() {
  load_deploy_env
  if [[ "${INSTALL_LOCAL_OLLAMA:-false}" != "true" ]]; then
    return
  fi

  run_with_sudo mkdir -p /etc/systemd/system/ollama.service.d
  run_with_sudo tee /etc/systemd/system/ollama.service.d/override.conf >/dev/null <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
  run_with_sudo systemctl daemon-reload
  run_with_sudo systemctl restart ollama
}

build_ocr_helper_if_enabled() {
  load_deploy_env
  if [[ "${OCRMYPDF_ENABLED:-true}" != "true" ]]; then
    return
  fi

  docker build \
    -t "${OCRMYPDF_DOCKER_IMAGE:-local-ai-ocrmypdf:latest}" \
    -f "${repo_root}/infra/ocrmypdf/Dockerfile" \
    "${repo_root}"
}

assert_docker_ready
ensure_deploy_env_file
ensure_project_directories
install_local_ollama_if_needed
configure_local_ollama_service_binding
build_ocr_helper_if_enabled

run_deploy_compose pull qdrant
run_deploy_compose up -d --build --remove-orphans

cat <<EOF
Deploy phase completed.

Next recommended step:
- ./scripts/deploy/ubuntu/verify.sh
EOF
