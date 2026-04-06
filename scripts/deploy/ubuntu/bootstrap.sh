#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "${script_dir}/../lib/common.sh"

assert_supported_os() {
  if [[ ! -f /etc/os-release ]]; then
    echo "Unsupported operating system. /etc/os-release was not found." >&2
    exit 1
  fi

  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "ubuntu" ]]; then
    echo "Installer v1 currently supports Ubuntu only. Detected: ${ID:-unknown}" >&2
    exit 1
  fi

  if [[ "${VERSION_ID:-}" != 24.04 && "${VERSION_ID:-}" != 24.10 && "${VERSION_ID:-}" != 24 ]]; then
    echo "Installer v1 is designed for Ubuntu 24.x. Detected: ${VERSION_ID:-unknown}" >&2
  fi
}

install_missing_packages() {
  local packages=(
    curl
    git
    ca-certificates
    docker.io
    docker-compose-v2
    tesseract-ocr
    tesseract-ocr-eng
    tesseract-ocr-swe
  )

  run_with_sudo apt-get update
  run_with_sudo apt-get install -y "${packages[@]}"
}

enable_docker_service() {
  run_with_sudo systemctl enable --now docker

  if [[ -n "${SUDO_USER:-}" ]] && id -nG "${SUDO_USER}" | grep -qw docker; then
    return
  fi

  if [[ -n "${SUDO_USER:-}" ]]; then
    run_with_sudo usermod -aG docker "${SUDO_USER}"
  fi
}

assert_supported_os
install_missing_packages
enable_docker_service
ensure_project_directories
ensure_deploy_env_file

cat <<EOF
Bootstrap phase completed.

Installed or verified:
- Docker Engine
- Docker Compose v2
- Git
- curl
- ca-certificates
- Tesseract OCR
- English and Swedish Tesseract language packs

Next recommended step:
- ./scripts/deploy/ubuntu/configure.sh
EOF
